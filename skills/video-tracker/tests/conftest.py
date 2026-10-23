"""Shared fixtures: synthetic video writer + config factory.

Synthetic videos are written with OpenCV's video writer so the tracker
tests can run a real CSRT loop without needing a real experiment video.
When OpenCV is not installed, the fixtures raise ``pytest.skip`` so the
rest of the suite (pure numpy / CSV / JSON / report paths) still runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest


def _cv2():
    try:
        import cv2
    except ImportError:
        pytest.skip("OpenCV not installed (opencv-contrib-python-headless)")
    return cv2


def make_synthetic_video(
    path: Path,
    n_frames: int = 40,
    fps: float = 30.0,
    width: int = 320,
    height: int = 240,
    object_track: tuple[str, float] = ("ball", 0.5),
) -> tuple[Path, dict]:
    """Write a synthetic BGR video with a moving bright square.

    Returns ``(path, meta)`` where *meta* contains the first-frame ROI for
    the object and the declared FPS, ready to build a config from.
    """
    cv2 = _cv2()
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
    assert out.isOpened(), f"could not open video writer for {path}"

    x0 = width // 2 - 12
    y0 = height // 2 - 12
    size = 24
    # Object position as a function of frame: a horizontal sine sweep.
    # object_track[1] is the temporal frequency in Hz, so the per-frame phase
    # increment is 2*pi*f/fps. (The earlier formula multiplied by n_frames,
    # which made the object teleport tens of pixels between frames and made
    # the smooth-tracking backends lose lock — a fixture bug, not a tracker
    # bug.)
    omega = 2 * np.pi * object_track[1] / fps
    for i in range(n_frames):
        canvas = np.full((height, width, 3), 30, dtype=np.uint8)
        cx = int(x0 + 12 + 40.0 * np.sin(omega * i))
        cy = y0 + 12
        canvas[
            max(0, cy - size // 2) : min(height, cy + size // 2),
            max(0, cx - size // 2) : min(width, cx + size // 2),
        ] = (80, 200, 255)
        out.write(canvas)
    out.release()
    meta = {
        "roi": (x0, y0, size, size),
        "fps": fps,
        "n_frames": n_frames,
        "width": width,
        "height": height,
    }
    return path, meta


def make_config_dict(video: Path, meta: dict, **overrides) -> dict:
    """Build a minimal, valid config dict for the synthetic video."""
    x, y, w, h = meta["roi"]
    base = {
        "videos": [str(video)],
        "objects": [{"name": "ball", "x": x, "y": y, "w": w, "h": h}],
        "fps": meta["fps"],
        "output": "./output",
    }
    base.update(overrides)
    return base


def write_json_config(tmp_path: Path, cfg: dict, name: str = "cfg.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p
