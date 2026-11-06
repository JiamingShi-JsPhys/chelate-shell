"""Object tracking with a pluggable backend and robustness layers.

The skill supports two backends:

* ``csrt``   — OpenCV's CSRT tracker (OpenCV 4.x, via ``TrackerCSRT_create``).
               Best accuracy, but **removed from OpenCV 5.x**.
* ``template`` — a pure ``cv2.matchTemplate`` tracker (core OpenCV, no external
               model files). Works on every OpenCV build including 5.x, and is
               the automatic fallback when CSRT is unavailable.

Both backends share a common robustness stack:

* **ROI fail-fast** — an out-of-frame ROI raises ``TrackingError`` at init.
* **Sub-pixel refinement** — a localized template match + parabolic peak
  interpolation nudges each reported centre below integer precision.
* **Optical-flow fallback** — when the tracker loses the target and the
  template re-acquire also fails, a dense Farneback flow estimate advances
  the last known centre instead of freezing it (configurable).
* **Auto-downscale** — frames larger than ``max_dim`` are tracked at reduced
  resolution and the positions are scaled back to original pixels.
* **Frame stepping** — only every ``frame_step``-th frame is recorded.

OpenCV is imported lazily so module import (and unit tests of the
non-cv2 parts) never require the full stack.
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, ObjectROI, TrackerParams
from .errors import ConfigError, TrackingError, VideoError


@dataclass
class TrajectoryPoint:
    frame: int
    time_s: float
    x_px: float
    y_px: float
    confidence: float
    reinit: bool

    def to_row(self) -> list:
        return [
            self.frame,
            round(self.time_s, 6),
            round(self.x_px, 3),
            round(self.y_px, 3),
            round(self.confidence, 4),
            self.reinit,
        ]


@dataclass
class ObjectResult:
    """Trajectory + quality metrics for one tracked object."""

    name: str
    roi: ObjectROI
    points: list[TrajectoryPoint] = field(default_factory=list)
    lost_frames: list[int] = field(default_factory=list)
    reinit_frames: list[int] = field(default_factory=list)
    tracker_losses: int = 0

    @property
    def success_rate(self) -> float:
        if not self.points:
            return 0.0
        ok = len(self.points) - len(self.lost_frames)
        return ok / len(self.points)

    def rows(self, scale: float | None = None) -> list[list]:
        """CSV rows; when *scale* (cm per pixel) is given, add cm columns."""
        out = []
        for p in self.points:
            row = p.to_row()
            if scale is not None:
                row += [round(p.x_px * scale, 3), round(p.y_px * scale, 3)]
            out.append(row)
        return out

    def positions_cm(self, scale: float) -> tuple[list[float], list[float], list[float]]:
        t = [p.time_s for p in self.points]
        x = [p.x_px * scale for p in self.points]
        y = [p.y_px * scale for p in self.points]
        return x, y, t

    def summary(self) -> dict:
        return {
            "object": self.name,
            "roi": {"x": self.roi.x, "y": self.roi.y, "w": self.roi.w, "h": self.roi.h},
            "frames_tracked": len(self.points),
            "lost_frames": list(self.lost_frames),
            "reinit_frames": list(self.reinit_frames),
            "tracker_losses": self.tracker_losses,
            "success_rate": round(self.success_rate, 4),
        }


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - env specific
        raise VideoError(
            "OpenCV is required for video tracking (pip install "
            "opencv-contrib-python-headless)"
        ) from exc
    return cv2


def _gray_enhance(cv2, frame) -> "np.ndarray":
    """Gaussian blur + CLAHE on the gray channel (Thomas-Kr scheme)."""
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _color_enhance(cv2, frame) -> "np.ndarray":
    """Per-channel CLAHE, keeping colour identity for template matching.

    The grayscale path collapses differently-coloured objects into identical
    bright-blob-on-dark-background patches after CLAHE, so a red disk and a
    green disk become indistinguishable and the tracker can silently swap
    them. Matching on the 3-channel colour-enhanced frame preserves colour
    identity (a red template does not correlate with a green disk), which is
    what makes multi-object tracking of colour-distinct targets correct.
    """
    if frame.ndim == 2:
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    ch = [clahe.apply(blurred[:, :, i]) for i in range(3)]
    return cv2.merge(ch)


def _parabolic_offset(res: "np.ndarray", px: int, py: int) -> tuple[float, float]:
    """Sub-pixel offset from the integer peak of a correlation surface.

    Fits a parabola through the peak and its two neighbours along each axis
    and returns ``(dx, dy)`` to add to the integer peak location.
    """
    H, W = res.shape[:2]
    dx = dy = 0.0
    if 1 <= px < W - 1:
        l = float(res[py, px - 1])
        c = float(res[py, px])
        r = float(res[py, px + 1])
        denom = l - 2 * c + r
        if denom != 0:
            dx = 0.5 * (l - r) / denom
    if 1 <= py < H - 1:
        u = float(res[py - 1, px])
        c = float(res[py, px])
        d = float(res[py + 1, px])
        denom = u - 2 * c + d
        if denom != 0:
            dy = 0.5 * (u - d) / denom
    return dx, dy


def _optical_flow_predict(cv2, prev_gray, cur_gray, cx: float, cy: float,
                          win: int = 21) -> "tuple[float, float] | None":
    """Estimate the (dx, dy) displacement at (cx, cy) via dense Farneback flow.

    Returns ``None`` when flow cannot be computed (missing frame, tiny window,
    or a cv2 error). The caller treats ``None`` as "fall back to freezing".
    """
    if prev_gray is None or cur_gray is None:
        return None
    h, w = prev_gray.shape[:2]
    x0 = max(0, int(cx - win))
    y0 = max(0, int(cy - win))
    x1 = min(w - 1, int(cx + win))
    y1 = min(h - 1, int(cy + win))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    pf = prev_gray[y0:y1, x0:x1].astype(np.float32)
    cf = cur_gray[y0:y1, x0:x1].astype(np.float32)
    try:
        flow = cv2.calcOpticalFlowFarneback(
            pf, cf, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
    except cv2.error:  # pragma: no cover - backend specific
        return None
    dx = float(np.mean(flow[..., 0]))
    dy = float(np.mean(flow[..., 1]))
    return dx, dy


class _BaseTracker:
    """Shared state + robustness helpers for both backends."""

    def __init__(self, cv2, roi: ObjectROI, first_frame, threshold: float):
        H, W = first_frame.shape[:2]
        if not roi_in_bounds(roi, W, H):
            raise TrackingError(
                f"object {roi.name!r} ROI {roi.bbox} is outside the frame "
                f"bounds {W}x{H}"
            )
        self.cv2 = cv2
        self.name = roi.name
        self.bbox = roi.bbox
        self.last_bbox = roi.bbox
        self.threshold = threshold
        self.lost = False
        self.tracker_losses = 0
        self.subpixel = True
        self.use_optical_flow = True
        self._last_gray = _gray_enhance(cv2, first_frame)
        self._last_color = _color_enhance(cv2, first_frame)
        self.template = self._build_template(self._last_color)

    def _build_template(self, frame):
        x, y, w, h = [int(v) for v in self.bbox]
        return frame[y : y + h, x : x + w].copy()

    def current_bbox(self):
        return self.bbox if not self.lost else self.last_bbox

    def _refine_subpixel(self, enhanced, bbox):
        """Return a sub-pixel-refined copy of *bbox* via local template match."""
        if not self.subpixel or self.template is None:
            return bbox
        x, y, w, h = [int(v) for v in bbox]
        margin = max(4, int(0.5 * w))
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(enhanced.shape[1], x + w + margin)
        y1 = min(enhanced.shape[0], y + h + margin)
        region = enhanced[y0:y1, x0:x1]
        th, tw = self.template.shape[:2]
        if region.shape[0] < th or region.shape[1] < tw:
            return bbox
        res = self.cv2.matchTemplate(region, self.template, self.cv2.TM_CCOEFF_NORMED)
        _, _, _, (mx, my) = self.cv2.minMaxLoc(res)
        dx, dy = _parabolic_offset(res, mx, my)
        top_x = x0 + mx + dx
        top_y = y0 + my + dy
        # Keep the sub-pixel precision (do NOT round to integer here).
        return (float(top_x), float(top_y), w, h)

    def _flow_fallback(self, enhanced):
        """Predict the new centre via optical flow; ``None`` if unavailable."""
        if not self.use_optical_flow:
            return None
        cx = self.last_bbox[0] + self.last_bbox[2] / 2
        cy = self.last_bbox[1] + self.last_bbox[3] / 2
        disp = _optical_flow_predict(self.cv2, self._last_gray, enhanced, cx, cy)
        if disp is None:
            return None
        dx, dy = disp
        x = self.last_bbox[0] + dx
        y = self.last_bbox[1] + dy
        cand = ObjectROI(self.name, int(x), int(y), self.last_bbox[2],
                         self.last_bbox[3])
        H, W = enhanced.shape[:2]
        if not roi_in_bounds(cand, W, H):
            return None
        return (int(round(x)), int(round(y)), self.last_bbox[2], self.last_bbox[3])


class _CSRTTracker(_BaseTracker):
    """OpenCV CSRT backend (OpenCV 4.x)."""

    def __init__(self, cv2, roi, first_frame, params: TrackerParams,
                 template_match: bool, threshold: float):
        super().__init__(cv2, roi, first_frame, threshold)
        self.params = params
        self.enabled = template_match
        try:
            self.tracker = cv2.TrackerCSRT_create(params.to_cv2())
            ret = self.tracker.init(first_frame, self.bbox)
        except cv2.error as exc:
            raise TrackingError(
                f"could not initialize CSRT tracker for object {roi.name!r} "
                f"with ROI {self.bbox}: {exc}"
            ) from exc
        if ret is False:
            raise TrackingError(
                f"could not initialize CSRT tracker for object {roi.name!r} "
                f"with ROI {self.bbox}"
            )

    def _new_tracker(self):
        try:
            t = self.cv2.TrackerCSRT_create(self.params.to_cv2())
            t.clear()
            return t
        except Exception:  # pragma: no cover - fallback path
            return self.cv2.TrackerCSRT_create(self.params.to_cv2())

    def update(self, frame, frame_idx: int):
        gray = _gray_enhance(self.cv2, frame)
        color = _color_enhance(self.cv2, frame)
        if not self.lost:
            ok, box = self.tracker.update(frame)
            if ok:
                self.bbox = tuple(int(v) for v in box)
                self.last_bbox = self.bbox
                self.bbox = self._refine_subpixel(color, self.bbox)
                self._last_gray = gray
                self._last_color = color
                return 1.0, False, False
            self.tracker_losses += 1
            self.lost = True
        if self.enabled and self.template is not None:
            conf, found = self._template_reacquire(color)
            if found:
                self.tracker = self._new_tracker()
                try:
                    self.tracker.init(frame, self.bbox)
                except self.cv2.error as exc:
                    raise TrackingError(
                        f"template re-init failed for object {self.name!r} "
                        f"at frame {frame_idx} with bbox {self.bbox}: {exc}"
                    ) from exc
                self.last_bbox = self.bbox
                self.lost = False
                self._last_gray = gray
                self._last_color = color
                return conf, True, True
        fb = self._flow_fallback(gray)
        if fb is not None:
            self.bbox = fb
            self.last_bbox = fb
            self._last_gray = gray
            self._last_color = color
            return 0.2, True, False
        self._last_gray = gray
        self._last_color = color
        return 0.0, True, False

    def _template_reacquire(self, color):
        """Locate the object via global colour-aware template matching."""
        result = self.cv2.matchTemplate(color, self.template,
                                         self.cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = self.cv2.minMaxLoc(result)
        if max_val >= self.threshold:
            x, y = max_loc
            self.bbox = (x, y, self.bbox[2], self.bbox[3])
            self.bbox = self._refine_subpixel(color, self.bbox)
            return float(max_val), True
        return float(max_val), False


class _TemplateTracker(_BaseTracker):
    """Pure template-matching backend (core OpenCV, 0 external files).

    Works on every OpenCV build including 5.x where CSRT was removed. Best
    for rigid, roughly constant-sized objects — exactly the skill's target.
    """

    def __init__(self, cv2, roi, first_frame, template_match: bool, threshold: float):
        super().__init__(cv2, roi, first_frame, threshold)
        self.enabled = True  # template matching is the primary mechanism
        self.search_margin = max(20, int(1.5 * roi.w))

    def update(self, frame, frame_idx: int):
        gray = _gray_enhance(self.cv2, frame)
        color = _color_enhance(self.cv2, frame)
        x, y, w, h = [int(v) for v in self.current_bbox()]
        margin = self.search_margin * (3 if self.lost else 1)
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(color.shape[1], x + w + margin)
        y1 = min(color.shape[0], y + h + margin)
        region = color[y0:y1, x0:x1]
        th, tw = self.template.shape[:2]
        if region.shape[0] < th or region.shape[1] < tw:
            return self._on_loss(gray, color)
        res = self.cv2.matchTemplate(region, self.template, self.cv2.TM_CCOEFF_NORMED)
        _, max_val, _, (mx, my) = self.cv2.minMaxLoc(res)
        if max_val < self.threshold:
            # Local search missed; try a full-frame re-acquire before giving up.
            re = self._global_reacquire(color)
            if re is not None:
                self.bbox = re
                self.last_bbox = re
                self.lost = False
                self._last_gray = gray
                self._last_color = color
                return float(max_val), True, True
            return self._on_loss(gray, color, max_val)
        bbox = (int(x0 + mx), int(y0 + my), w, h)
        bbox = self._refine_subpixel(color, bbox)
        self.bbox = bbox
        self.last_bbox = bbox
        self.lost = False
        self._last_gray = gray
        self._last_color = color
        return float(max_val), False, False

    def _global_reacquire(self, color):
        """Full-frame colour-aware template re-locate."""
        res = self.cv2.matchTemplate(color, self.template,
                                     self.cv2.TM_CCOEFF_NORMED)
        _, max_val, _, (mx, my) = self.cv2.minMaxLoc(res)
        if max_val >= self.threshold:
            x, y, w, h = [int(v) for v in self.bbox]
            bbox = (int(mx), int(my), w, h)
            return self._refine_subpixel(color, bbox)
        return None

    def _on_loss(self, gray, color, score: float = 0.0):
        self.tracker_losses += 1
        self.lost = True
        fb = self._flow_fallback(gray)
        if fb is not None:
            self.bbox = fb
            self.last_bbox = fb
            self._last_gray = gray
            self._last_color = color
            return 0.2, True, False
        self._last_gray = gray
        self._last_color = color
        return 0.0, True, False


# Keep the historical name importable (used by tests + docs).
_CV2Tracker = _CSRTTracker


def create_tracker(cv2, roi: ObjectROI, first_frame, params: TrackerParams,
                   template_match: bool, threshold: float,
                   tracker_type: str) -> "_BaseTracker":
    """Resolve the backend for *tracker_type* on the running OpenCV build."""
    want = str(tracker_type).lower()
    if (want in ("auto", "csrt")) and hasattr(cv2, "TrackerCSRT_create"):
        return _CSRTTracker(cv2, roi, first_frame, params, template_match, threshold)
    if want == "csrt":
        raise VideoError(
            "tracker_type='csrt' requested but this OpenCV build has no "
            "TrackerCSRT_create (OpenCV 5.x removed CSRT). Use 'auto' or "
            "'template' instead."
        )
    return _TemplateTracker(cv2, roi, first_frame, template_match, threshold)


def _open_video(cv2, path: Path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError(f"could not open video: {path}")
    return cap


def track_video(
    config: Config,
    video_index: int = 0,
) -> tuple[dict, list[ObjectResult]]:
    """Track all declared objects in ``config.videos[video_index]``.

    Returns ``(summary, results)`` where *results* holds one
    :class:`ObjectResult` per declared object and *summary* carries
    video-level metadata (FPS, frame count, lost-frame lists, success
    rates, and cm-scaled positions when a scale was declared).
    """
    cv2 = _require_cv2()
    cfg = config
    if video_index >= len(cfg.videos):
        raise ConfigError(
            f"video index {video_index} out of range (have {len(cfg.videos)})"
        )
    path = cfg.videos[video_index]
    cap = _open_video(cv2, path)
    fps_native = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cfg.fps) if cfg.fps is not None else (
        fps_native if fps_native > 0 else 30.0
    )

    ret, first = cap.read()
    if not ret:
        cap.release()
        raise VideoError(f"no frames in video: {path}")

    orig_H, orig_W = first.shape[:2]

    # Optional event-window: track only frames [start, end] (inclusive).
    frame_start, frame_end = (cfg.frame_range or (0, total - 1))
    frame_start = max(0, min(frame_start, total - 1))
    frame_end = max(frame_start, min(frame_end, total - 1))

    if frame_start > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_start))
        ret, first = cap.read()
        if not ret:
            cap.release()
            raise VideoError(f"could not seek to frame {frame_start} in {path}")

    # Optional auto-downscale for speed / robustness on large frames.
    scale = 1.0
    if cfg.max_dim and max(orig_H, orig_W) > cfg.max_dim:
        scale = cfg.max_dim / max(orig_H, orig_W)
        first = cv2.resize(first, (int(orig_W * scale), int(orig_H * scale)))

    def _scale_roi(roi: ObjectROI) -> ObjectROI:
        return ObjectROI(
            roi.name,
            int(roi.x * scale),
            int(roi.y * scale),
            max(1, int(roi.w * scale)),
            max(1, int(roi.h * scale)),
        )

    trackers = [
        create_tracker(cv2, _scale_roi(roi), first, cfg.params,
                      cfg.use_template_reinit, cfg.template_match_threshold,
                      cfg.tracker_type)
        for roi in cfg.objects
    ]
    for tr in trackers:
        tr.subpixel = cfg.subpixel
        tr.use_optical_flow = cfg.use_optical_flow_fallback

    H, W = first.shape[:2]
    results: list[ObjectResult] = []
    for roi, tr in zip(cfg.objects, trackers):
        res = ObjectResult(name=roi.name, roi=roi)
        results.append(res)
        # The initialisation frame: record the declared ROI centre. Frame
        # numbers stay source-absolute so a row maps back to the source file,
        # but the time axis is shifted so time_s == 0.0 at the window start.
        cx0 = roi.x + roi.w / 2
        cy0 = roi.y + roi.h / 2
        res.points.append(TrajectoryPoint(frame_start, 0.0, cx0, cy0, 1.0, False))
        if tr.lost:
            res.lost_frames.append(frame_start)

    frame_idx = frame_start
    processed = 0
    while frame_idx < frame_end:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        processed += 1
        if scale != 1.0:
            frame = cv2.resize(
                frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale))
            )
        time_s = (frame_idx - frame_start) / fps
        record = (processed % cfg.frame_step == 0) or (frame_idx == frame_end)
        for roi, tr, res in zip(cfg.objects, trackers, results):
            conf, was_lost, did_reinit = tr.update(frame, frame_idx)
            x, y, w, h = tr.current_bbox()
            # Scale the recorded centre back to original pixel coordinates.
            cx = (x + w / 2) / scale
            cy = (y + h / 2) / scale
            if record:
                res.points.append(
                    TrajectoryPoint(frame_idx, time_s, cx, cy, conf, did_reinit)
                )
                if was_lost:
                    res.lost_frames.append(frame_idx)
                if did_reinit:
                    res.reinit_frames.append(frame_idx)
        del frame

    cap.release()

    if cfg.scale_cm_per_px is not None:
        for res in results:
            x_cm, y_cm, _t = res.positions_cm(cfg.scale_cm_per_px)
            res._x_cm = x_cm  # type: ignore[attr-defined]
            res._y_cm = y_cm  # type: ignore[attr-defined]

    summary = {
        "video": str(path),
        "fps": fps,
        "fps_source": "config" if cfg.fps is not None else "container",
        "n_frames": processed + 1,
        "frame_width": orig_W,
        "frame_height": orig_H,
        "objects": [res.summary() for res in results],
        "scale_cm_per_px": cfg.scale_cm_per_px,
    }
    if cfg.frame_range is not None:
        summary["frame_range"] = [frame_start, frame_end]
    if cfg.max_dim is not None and scale != 1.0:
        summary["downscale"] = {
            "max_dim": cfg.max_dim,
            "scale": round(scale, 6),
            "tracked_dim": [W, H],
        }
    return summary, results


def roi_in_bounds(roi: ObjectROI, width: int, height: int) -> bool:
    """A ROI must lie fully inside a frame of the given size."""
    return (
        roi.x >= 0
        and roi.y >= 0
        and roi.x + roi.w <= width
        and roi.y + roi.h <= height
    )
