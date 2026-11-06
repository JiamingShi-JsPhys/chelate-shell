"""Tests for config loading / validation / TrackerParams."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.config import (
    Config,
    ObjectROI,
    TrackerParams,
    _parse_frame_range,
    _parse_objects,
    _parse_params,
    load_config,
)
from scripts.errors import ConfigError, VideoError


def test_load_config_from_dict():
    cfg = load_config(
        {
            "videos": ["./videos/a.mp4"],
            "objects": [{"name": "ball", "x": 1, "y": 2, "w": 3, "h": 4}],
            "fps": 24.0,
        }
    )
    assert cfg.videos == [Path("./videos/a.mp4")]
    assert cfg.objects[0].name == "ball"
    assert cfg.objects[0].bbox == (1, 2, 3, 4)
    assert cfg.fps == 24.0


def test_load_config_single_video_string():
    cfg = load_config(
        {
            "video": "./one.avi",
            "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
        }
    )
    assert cfg.videos == [Path("./one.avi")]


def test_load_config_defaults():
    cfg = load_config(
        {
            "videos": ["./a.mp4"],
            "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
        }
    )
    assert cfg.fps is None
    assert cfg.scale_cm_per_px is None
    assert cfg.template_match_threshold == 0.85
    assert cfg.use_template_reinit is True
    assert cfg.fft_max_freq is None
    assert cfg.fft_top_peaks == 10
    assert cfg.output == Path("output")


def test_load_config_missing_videos():
    with pytest.raises(ConfigError):
        load_config({"objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}]})


def test_load_config_empty_objects():
    with pytest.raises(ConfigError):
        load_config({"videos": ["./a.mp4"], "objects": []})


def test_load_config_missing_video_file(tmp_path):
    with pytest.raises(VideoError):
        cfg = load_config(
            {
                "videos": [str(tmp_path / "nope.mp4")],
                "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
            }
        )
        cfg.validate()


def test_load_config_unsupported_format(tmp_path):
    p = tmp_path / "movie.txt"
    p.write_text("not a video")
    with pytest.raises(ConfigError):
        load_config(
            {
                "videos": [str(p)],
                "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
            }
        )


def test_load_config_bad_threshold():
    with pytest.raises(ConfigError):
        load_config(
            {
                "videos": ["./a.mp4"],
                "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
                "template_match_threshold": 1.5,
            }
        )


def test_load_config_zero_fft_top_peaks():
    with pytest.raises(ConfigError):
        load_config(
            {
                "videos": ["./a.mp4"],
                "objects": [{"name": "o", "x": 0, "y": 0, "w": 1, "h": 1}],
                "fft_top_peaks": 0,
            }
        )


def test_load_config_json_string():
    cfg = load_config(
        '{"videos": ["./a.mp4"], "objects": [{"name": "o", "x": 0, "y": 0, '
        '"w": 1, "h": 1}], "fps": 12}'
    )
    assert cfg.fps == 12.0


def test_load_config_bad_json_string():
    with pytest.raises(ConfigError):
        load_config("{not: json")


def test_load_config_missing_file():
    with pytest.raises(ConfigError):
        load_config("./does-not-exist.json")


def test_load_config_yaml_requires_pyyaml(tmp_path):
    pytest.importorskip("yaml", reason="PyYAML not installed")

    p = tmp_path / "c.yaml"
    p.write_text(
        "videos:\n  - ./a.mp4\nobjects:\n  - name: o\n    x: 0\n    y: 0\n"
        "    w: 1\n    h: 1\n",
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.objects[0].name == "o"


def test_load_config_yaml_without_pyyaml(tmp_path, monkeypatch):
    p = tmp_path / "c.yaml"
    p.write_text("videos:\n  - ./a.mp4\n")
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("no yaml")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ConfigError, match="PyYAML"):
        load_config(p)


def test_parse_objects_missing_key():
    with pytest.raises(ConfigError):
        _parse_objects([{"x": 0, "y": 0, "w": 1, "h": 1}])


def test_parse_objects_non_mapping():
    with pytest.raises(ConfigError):
        _parse_objects(["ball"])


def test_parse_params_unknown_field():
    with pytest.raises(ConfigError):
        _parse_params({"bogus_field": 1})


def test_parse_params_bad_psr():
    with pytest.raises(ConfigError):
        _parse_params({"psr_threshold": 0.0})


def test_parse_params_bad_admm():
    with pytest.raises(ConfigError):
        _parse_params({"admm_iterations": 0})


def test_parse_params_bad_template_size():
    with pytest.raises(ConfigError):
        _parse_params({"template_size": 4})


def test_tracker_params_to_cv2():
    cv2 = pytest.importorskip("cv2")
    p = TrackerParams(psr_threshold=0.07, admm_iterations=2,
                      template_size=100, padding=3.0,
                      scale_lr=0.025, window_function="hann")
    cv2_params = p.to_cv2()
    assert cv2_params.psr_threshold == pytest.approx(0.07)
    assert cv2_params.admm_iterations == 2
    assert cv2_params.template_size == pytest.approx(100)


def test_tracker_params_stock_defaults():
    p = TrackerParams()
    assert p.psr_threshold == pytest.approx(0.035)
    assert p.admm_iterations == 4
    assert p.template_size == 200
    assert p.padding == pytest.approx(3.0)
    assert p.scale_lr == pytest.approx(0.025)
    assert p.window_function == "hann"


def test_object_roi_bbox():
    roi = ObjectROI("a", 1, 2, 3, 4)
    assert roi.bbox == (1, 2, 3, 4)


# --- frame_range parsing --------------------------------------------------- #
def test_frame_range_absent():
    assert _parse_frame_range(None) is None


def test_frame_range_list():
    assert _parse_frame_range([10, 20]) == (10, 20)


def test_frame_range_dict():
    assert _parse_frame_range({"start": 5, "end": 8}) == (5, 8)


def test_frame_range_end_before_start():
    with pytest.raises(ConfigError):
        _parse_frame_range([20, 10])


def test_frame_range_negative_start():
    with pytest.raises(ConfigError):
        _parse_frame_range([-1, 10])


def test_frame_range_malformed():
    with pytest.raises(ConfigError):
        _parse_frame_range([1, 2, 3])
    with pytest.raises(ConfigError):
        _parse_frame_range("not a list")
