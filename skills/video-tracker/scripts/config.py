"""Configuration loading and validation for video-tracker.

A config is a JSON or YAML mapping. JSON works with the standard library
alone; YAML configs additionally require ``pyyaml``. OpenCV / numpy are
hard requirements for actual video processing and are checked lazily by
the modules that use them so that config parsing and the FFT math (which
only needs numpy) stay testable without the full stack.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigError, VideoError

SUPPORTED_VIDEO_EXTS = {".mp4", ".avi", ".mov"}


@dataclass
class TrackerParams:
    """CSRT tracker tuning knobs (exposed via OpenCV's TrackerCSRT_Params).

    All fields default to the OpenCV stock values so an empty config block
    reproduces stock behaviour.
    """

    psr_threshold: float = 0.035
    admm_iterations: int = 4
    template_size: int = 200
    padding: float = 3.0
    scale_lr: float = 0.025
    window_function: str = "hann"

    def to_cv2(self):
        """Return a cv2 TrackerCSRT_Params, or a compatible namespace on 5.x.

        OpenCV 5.x removed ``cv2.TrackerCSRT_Params`` (and CSRT itself), so on
        those builds we return a lightweight ``types.SimpleNamespace`` carrying
        the same fields. This keeps the params round-trip testable everywhere
        and is harmless on 5.x because the CSRT backend is never instantiated
        there (the tracker factory falls back to template matching).
        """
        import cv2

        if hasattr(cv2, "TrackerCSRT_Params"):
            p = cv2.TrackerCSRT_Params()
            p.psr_threshold = self.psr_threshold
            p.admm_iterations = self.admm_iterations
            p.template_size = self.template_size
            p.padding = self.padding
            p.scale_lr = self.scale_lr
            p.window_function = self.window_function
            return p
        from types import SimpleNamespace

        return SimpleNamespace(
            psr_threshold=self.psr_threshold,
            admm_iterations=self.admm_iterations,
            template_size=self.template_size,
            padding=self.padding,
            scale_lr=self.scale_lr,
            window_function=self.window_function,
        )


@dataclass
class ObjectROI:
    """Region of interest for one tracked object, in pixels (x, y, w, h)."""

    name: str
    x: int
    y: int
    w: int
    h: int

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)


@dataclass
class Config:
    """Validated experiment configuration."""

    videos: list[Path] = field(default_factory=list)
    objects: list[ObjectROI] = field(default_factory=list)
    fps: float | None = None
    scale_cm_per_px: float | None = None
    frame_range: tuple[int, int] | None = None  # (start, end) inclusive
    params: TrackerParams = field(default_factory=TrackerParams)
    template_match_threshold: float = 0.85
    use_template_reinit: bool = True
    fft_max_freq: float | None = None
    fft_top_peaks: int = 10
    tracker_type: str = "auto"            # auto | csrt | template
    subpixel: bool = True                 # sub-pixel centroid refinement
    use_optical_flow_fallback: bool = True  # flow-predict on tracker loss
    max_dim: int | None = None            # auto-downscale long edge above this
    frame_step: int = 1                   # record every Nth frame
    output: Path = Path("output")

    def validate(self, require_fps: bool = False) -> None:
        for v in self.videos:
            if not Path(v).exists():
                raise VideoError(f"video not found: {v}")
        for o in self.objects:
            if o.w <= 0 or o.h <= 0:
                raise ConfigError(f"object {o.name!r}: w/h must be positive")
        if require_fps and self.fps is None:
            raise ConfigError(
                "fps is required (declare it in config); the video's "
                "container FPS is not trusted for timing"
            )


def _as_path(v: Any, default: str | None = None) -> Path:
    if v is None:
        if default is None:
            raise ConfigError("expected a path value")
        return Path(default)
    return Path(str(v))


def _parse_objects(raw: Any) -> list[ObjectROI]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("objects must be a non-empty list")
    out: list[ObjectROI] = []
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConfigError(f"objects[{i}] must be a mapping")
        try:
            obj = ObjectROI(
                name=str(item["name"]),
                x=int(item["x"]),
                y=int(item["y"]),
                w=int(item["w"]),
                h=int(item["h"]),
            )
        except KeyError as missing:
            raise ConfigError(
                f"objects[{i}] missing key {missing.args[0]!r}; "
                "each object needs name/x/y/w/h"
            ) from None
        out.append(obj)
    return out


def _parse_params(raw: Any) -> TrackerParams:
    p = TrackerParams()
    if not raw:
        return p
    if not isinstance(raw, Mapping):
        raise ConfigError("params must be a mapping")
    known = set(p.__dataclass_fields__)  # type: ignore[attr-defined]
    for k, v in raw.items():
        if k not in known:
            raise ConfigError(f"unknown tracker param {k!r}; valid: {sorted(known)}")
        if k == "window_function":
            v = str(v)
        elif k in ("psr_threshold", "padding", "scale_lr"):
            v = float(v)
        else:
            v = int(v)
        setattr(p, k, v)
    if p.psr_threshold <= 0:
        raise ConfigError("psr_threshold must be > 0")
    if p.admm_iterations < 1:
        raise ConfigError("admm_iterations must be >= 1")
    if p.template_size < 16:
        raise ConfigError("template_size must be >= 16")
    return p


def _load_raw(source: Any) -> dict:
    """Load config from a dict, a JSON/YAML path, or a JSON string."""
    if isinstance(source, Mapping):
        return dict(source)
    if isinstance(source, str):
        stripped = source.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"config string is not valid JSON: {exc}") from exc
        source = Path(stripped)
    path = Path(str(source))
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise ConfigError(
                "YAML config requires PyYAML (pip install pyyaml); "
                "or provide a JSON config instead"
            ) from exc
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"config is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")
    return data


def load_config(source: Any) -> Config:
    """Build and validate a :class:`Config` from dict / JSON / YAML source.

    Structural validation (object shape, threshold range, peak count,
    supported video formats) happens here so misuse fails fast. File
    existence is checked by :meth:`Config.validate`, which runs against
    real paths at execution time.
    """
    raw = _load_raw(source)

    videos_raw = raw.get("videos") or raw.get("video")
    if not videos_raw:
        raise ConfigError("config must declare 'videos' (list of paths)")
    if isinstance(videos_raw, (str, Path)):
        videos_raw = [videos_raw]
    if not isinstance(videos_raw, list):
        raise ConfigError("'videos' must be a list of paths (or a single path)")
    videos = [_as_path(v) for v in videos_raw]

    objects = _parse_objects(raw.get("objects"))
    params = _parse_params(raw.get("params"))

    threshold = float(raw.get("template_match_threshold", 0.85))
    if not (0.0 < threshold <= 1.0):
        raise ConfigError("template_match_threshold must be in (0, 1]")
    top_peaks = int(raw.get("fft_top_peaks", 10))
    if top_peaks < 1:
        raise ConfigError("fft_top_peaks must be >= 1")
    tracker_type = str(raw.get("tracker_type", "auto")).lower()
    if tracker_type not in ("auto", "csrt", "template"):
        raise ConfigError(
            f"tracker_type must be auto|csrt|template, got {tracker_type!r}"
        )
    subpixel = bool(raw.get("subpixel", True))
    use_optical_flow_fallback = bool(raw.get("use_optical_flow_fallback", True))
    max_dim = raw.get("max_dim")
    if max_dim is not None:
        max_dim = int(max_dim)
        if max_dim < 16:
            raise ConfigError("max_dim must be >= 16")
    frame_step = int(raw.get("frame_step", 1))
    if frame_step < 1:
        raise ConfigError("frame_step must be >= 1")
    for v in videos:
        ext = v.suffix.lower()
        if ext not in SUPPORTED_VIDEO_EXTS:
            raise ConfigError(
                f"unsupported video format {ext!r}; "
                f"supported: {sorted(SUPPORTED_VIDEO_EXTS)}"
            )

    frame_range = _parse_frame_range(raw.get("frame_range"))

    return Config(
        videos=videos,
        objects=objects,
        fps=raw.get("fps"),
        scale_cm_per_px=raw.get("scale_cm_per_px"),
        frame_range=frame_range,
        params=params,
        template_match_threshold=threshold,
        use_template_reinit=bool(raw.get("use_template_reinit", True)),
        fft_max_freq=raw.get("fft_max_freq"),
        fft_top_peaks=top_peaks,
        tracker_type=tracker_type,
        subpixel=subpixel,
        use_optical_flow_fallback=use_optical_flow_fallback,
        max_dim=max_dim,
        frame_step=frame_step,
        output=_as_path(raw.get("output"), "output"),
    )


def _parse_frame_range(raw: Any) -> tuple[int, int] | None:
    """Parse ``frame_range: [start, end]`` (inclusive) into a tuple.

    Accepts a two-element list/tuple of ints, a bare dict
    ``{"start": i, "end": j}``, or ``None`` (track the whole video).
    Validates that ``start >= 0`` and ``end >= start``.
    """
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        try:
            start = int(raw["start"])
            end = int(raw["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(
                f"frame_range mapping needs 'start' and 'end' ints: {exc}"
            ) from exc
    elif isinstance(raw, (list, tuple)) and len(raw) == 2:
        start, end = raw
        try:
            start, end = int(start), int(end)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"frame_range must be [int, int]: {exc}") from exc
    else:
        raise ConfigError(
            "frame_range must be [start, end] (two ints) or a mapping "
            "with 'start'/'end'"
        )
    if start < 0:
        raise ConfigError(f"frame_range start must be >= 0 (got {start})")
    if end < start:
        raise ConfigError(
            f"frame_range end ({end}) must be >= start ({start})"
        )
    return (start, end)
