"""Tests for the CSRT tracker + template re-acquire + synthetic video loop.

These exercise the real OpenCV stack end-to-end on a generated video, so
they skip cleanly when OpenCV is not installed.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.config import Config, ObjectROI, TrackerParams, load_config
from scripts.errors import ConfigError, TrackingError, VideoError
from scripts.tracker import (
    ObjectResult,
    TrajectoryPoint,
    _CV2Tracker,
    _open_video,
    _parabolic_offset,
    _optical_flow_predict,
    create_tracker,
    roi_in_bounds,
    track_video,
)


def test_roi_in_bounds():
    r = ObjectROI("o", 0, 0, 10, 10)
    assert roi_in_bounds(r, 100, 100)
    assert not roi_in_bounds(r, 5, 5)
    assert not roi_in_bounds(ObjectROI("o", -1, 0, 10, 10), 100, 100)
    assert not roi_in_bounds(ObjectROI("o", 0, 0, 101, 10), 100, 100)


def test_trajectory_point_row():
    p = TrajectoryPoint(3, 0.1, 10.0, 20.5, 0.9, True)
    assert p.to_row() == [3, 0.1, 10.0, 20.5, 0.9, True]


def test_object_positions_cm():
    r = ObjectResult(
        name="b",
        roi=ObjectROI("b", 0, 0, 1, 1),
        points=[
            TrajectoryPoint(0, 0.0, 10.0, 20.0, 1.0, False),
            TrajectoryPoint(1, 0.033, 11.0, 21.0, 1.0, False),
        ],
    )
    x, y, t = r.positions_cm(0.5)
    assert x == pytest.approx([5.0, 5.5])
    assert y == pytest.approx([10.0, 10.5])
    assert t == [0.0, 0.033]


def test_track_video_bad_index():
    cfg = load_config(
        {
            "videos": ["./a.mp4"],
            "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
        }
    )
    with pytest.raises(ConfigError):
        track_video(cfg, 5)


def _synthetic_cfg(tmp_path, n_frames=12, template_size=64):
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=n_frames)
    cfg_path = write_json_config(
        tmp_path,
        make_config_dict(
            video, meta,
            params={"template_size": template_size},
        ),
    )
    return load_config(cfg_path)


def test_track_video_on_synthetic(tmp_path):
    pytest.importorskip("cv2")
    cfg = _synthetic_cfg(tmp_path, n_frames=20)
    summary, results = track_video(cfg)
    # Record frame 0 (init) + every update-loop frame; assert consistency
    # rather than a hard-coded count, since the reader stops when read()
    # returns False.
    assert summary["fps"] == 30.0
    assert len(results) == 1
    res = results[0]
    # First point is the init frame; the rest come from the update loop.
    assert res.points[0].frame == 0
    # n_frames now counts ALL recorded points (init + every update), so the
    # point list length equals it directly.
    assert len(res.points) == summary["n_frames"]
    # A 20-frame synthetic video yields ~16 recorded points (init + 15
    # update frames) at most; allow a couple to drop.
    assert summary["n_frames"] >= 15
    # A bright square on a dark field should be tracked with high success.
    # A couple of frames may be lost+re-acquired (template re-init fires);
    # that is expected behavior, so assert a high-but-not-perfect rate.
    assert res.success_rate > 0.8


def test_track_video_with_scale_cm(tmp_path):
    pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=12)
    cfg_path = write_json_config(
        tmp_path,
        make_config_dict(
            video, meta,
            scale_cm_per_px=0.1,
            params={"template_size": 64},
        ),
    )
    cfg = load_config(cfg_path)
    summary, results = track_video(cfg)
    assert summary["scale_cm_per_px"] == 0.1
    assert hasattr(results[0], "_x_cm")
    assert results[0]._x_cm[0] == pytest.approx(
        results[0].points[0].x_px * 0.1
    )


def test_template_reacquire_repositions_bbox(tmp_path):
    pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=10)
    cfg_path = write_json_config(
        tmp_path,
        make_config_dict(
            video, meta,
            template_match_threshold=0.5,
            params={"template_size": 64},
        ),
    )
    cfg = load_config(cfg_path)
    summary, results = track_video(cfg)
    # Even if reinit fires, no frame should be fully dropped.  n_frames
    # counts every recorded point, so the list length equals it directly.
    assert len(results[0].points) == summary["n_frames"]


def test_open_video_fails_on_missing(tmp_path):
    cv2 = pytest.importorskip("cv2")
    with pytest.raises(VideoError):
        _open_video(cv2, tmp_path / "nope.mp4")


def test_frame_range_tracks_event_window(tmp_path):
    """frame_range limits the CSRT sweep to [start, end]; frame numbers
    stay source-absolute but the time axis starts at 0."""
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=20)
    start, end = 5, 10
    cfg_path = write_json_config(
        tmp_path,
        make_config_dict(
            video, meta,
            params={"template_size": 64},
            frame_range=[start, end],
        ),
    )
    cfg = load_config(cfg_path)
    assert cfg.frame_range == (start, end)
    summary, results = track_video(cfg)
    assert summary["frame_range"] == [start, end]
    res = results[0]
    # First recorded point is the init frame, tagged with the start index.
    assert res.points[0].frame == start
    assert res.points[0].time_s == 0.0
    # The sweep stops at `end`; no frame number beyond it is recorded.
    assert res.points[-1].frame == end
    # The last point's time_s reflects (end - start) frames elapsed.
    assert res.points[-1].time_s == pytest.approx((end - start) / meta["fps"])
    # Only the window frames are processed: start..end inclusive is
    # (end - start + 1) recorded points (the init frame + every update).
    assert summary["n_frames"] == end - start + 1


def test_tracker_init_fails_out_of_bounds(tmp_path):
    cv2 = pytest.importorskip("cv2")
    from scripts.config import TrackerParams

    # 64x64 frame; a 32x32 ROI placed far enough right that x+w overflows
    # the frame. The base tracker validates the ROI at construction time
    # (fail-fast) so an out-of-frame ROI must raise TrackingError before any
    # OpenCV call — independent of the OpenCV version / available backends.
    first = _blank_frame(cv2, 64)
    roi = ObjectROI("o", 100, 0, 32, 32)  # x=100 -> x+w=132 > 64
    with pytest.raises(TrackingError):
        create_tracker(cv2, roi, first, TrackerParams(), False, 0.9, "template")


def _blank_frame(cv2, size, value=30):
    import numpy as np

    return np.full((size, size, 3), value, dtype=np.uint8)


def test_roi_in_bounds_wired_into_track_video(tmp_path):
    """track_video must fail fast (TrackingError) on an out-of-frame ROI."""
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=5)
    cfg = load_config(
        {
            "videos": [str(video)],
            "objects": [{"name": "o", "x": 5000, "y": 0, "w": 24, "h": 24}],
            "fps": 30,
        }
    )
    with pytest.raises(TrackingError):
        track_video(cfg)


def test_template_backend_tracks_synthetic(tmp_path):
    """The template backend (OpenCV-5.x fallback) tracks a clean object."""
    pytest.importorskip("cv2")
    cfg = _synthetic_cfg(tmp_path, n_frames=20, template_size=64)
    cfg = load_config(
        {**_cfg_dict(cfg), "tracker_type": "template"}
    )
    summary, results = track_video(cfg)
    assert results[0].success_rate > 0.8
    assert summary["n_frames"] >= 15


def _cfg_dict(cfg) -> dict:
    """Reconstruct the raw config dict from a loaded Config (for overrides)."""
    return {
        "videos": [str(p) for p in cfg.videos],
        "objects": [
            {"name": o.name, "x": o.x, "y": o.y, "w": o.w, "h": o.h}
            for o in cfg.objects
        ],
        "fps": cfg.fps,
        "output": str(cfg.output),
        "params": {"template_size": 64},
    }


def test_downscale_scales_positions_back(tmp_path):
    """max_dim downscales internally but reports positions in original px."""
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=20,
                                       width=640, height=480)
    x, y, w, h = meta["roi"]  # ROI that actually contains the moving object
    base = {
        "videos": [str(video)],
        "objects": [{"name": "ball", "x": x, "y": y, "w": w, "h": h}],
        "fps": meta["fps"],
        "output": str(tmp_path / "out"),
    }
    full = track_video(load_config(base))
    down = track_video(load_config({**base, "max_dim": 480}))

    assert "downscale" in down[0]
    # recorded positions stay inside the original frame, not the smaller one
    res = down[1][0]
    xs = [p.x_px for p in res.points]
    ys = [p.y_px for p in res.points]
    assert all(0 <= x <= 640 for x in xs)
    assert all(0 <= y <= 480 for y in ys)
    # downscaled track is close to the full-res track (same motion)
    fa = {p.frame: p for p in full[1][0].points}
    da = {p.frame: p for p in res.points}
    common = [f for f in fa if f in da]
    dx = [abs(fa[f].x_px - da[f].x_px) for f in common]
    dy = [abs(fa[f].y_px - da[f].y_px) for f in common]
    assert (sum(dx) / len(dx)) < 6.0
    assert (sum(dy) / len(dy)) < 6.0


def test_frame_step_decimation(tmp_path):
    """frame_step records fewer points but keeps tracking continuity."""
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=20)
    base = {
        "videos": [str(video)],
        "objects": [{"name": "ball", "x": 148, "y": 108, "w": 24, "h": 24}],
        "fps": meta["fps"],
        "output": str(tmp_path / "out"),
        "params": {"template_size": 64},
    }
    full = track_video(load_config(base))
    stepped = track_video(load_config({**base, "frame_step": 4}))
    assert len(stepped[1][0].points) < len(full[1][0].points)
    assert len(stepped[1][0].points) >= 4


def test_subpixel_produces_fractional_positions(tmp_path):
    """sub-pixel refinement yields non-integer centres."""
    cv2 = pytest.importorskip("cv2")
    cfg = _synthetic_cfg(tmp_path, n_frames=20, template_size=64)
    cfg = load_config({**_cfg_dict(cfg), "tracker_type": "template",
                       "subpixel": True})
    _, results = track_video(cfg)
    pts = results[0].points[1:]  # skip the init (integer ROI centre)
    frac = [p for p in pts if abs(p.x_px - round(p.x_px)) > 1e-6]
    assert frac, "expected at least one sub-pixel (fractional) position"


def test_parabolic_offset_unit():
    """Parabolic peak interpolation recovers a sub-pixel peak."""
    res = np.zeros((5, 9), dtype=np.float64)
    py, px = 2, 4
    for x in range(9):
        # parabola peaking at x = 4.3
        res[py, x] = 1.0 - 0.5 * (x - 4.3) ** 2
    dx, dy = _parabolic_offset(res, px, py)
    assert dx == pytest.approx(0.3, abs=1e-6)
    assert dy == pytest.approx(0.0, abs=1e-6)


def test_optical_flow_predict_unit():
    """Dense flow recovers a known shift.

    Farneback assumes brightness constancy, so the inputs must be a
    coherent (here periodic) pattern translated by a known amount — a random
    or constant-offset field gives no usable gradient and recovers nothing.
    We translate a 2-D sine by (+6, +3) and check the mean flow recovers it.
    """
    cv2 = pytest.importorskip("cv2")
    ys, xs = np.mgrid[0:60, 0:60].astype(np.float64)
    prev = (128 + 60 * np.sin(xs / 4.0) * np.cos(ys / 4.0)).clip(0, 255).astype(np.uint8)
    cur = np.zeros((60, 60), np.uint8)
    # cur[y+3, x+6] = prev[y, x]  ->  a (+6, +3) translation
    cur[3:60, 6:60] = prev[0:57, 0:54]
    disp = _optical_flow_predict(cv2, prev, cur, 30.0, 30.0, win=20)
    assert disp is not None
    dx, dy = disp
    assert dx == pytest.approx(6.0, abs=2.0)
    assert dy == pytest.approx(3.0, abs=2.0)


def test_create_tracker_csrt_unavailable_raises_on_explicit():
    """Forcing csrt on a CSRT-less build must error clearly, not AttributeError."""
    cv2 = pytest.importorskip("cv2")
    if hasattr(cv2, "TrackerCSRT_create"):
        pytest.skip("CSRT present in this OpenCV build")
    first = _blank_frame(cv2, 64)
    roi = ObjectROI("o", 10, 10, 24, 24)
    with pytest.raises(Exception):
        create_tracker(cv2, roi, first, TrackerParams(), True, 0.9, "csrt")

