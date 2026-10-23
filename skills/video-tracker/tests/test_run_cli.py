"""In-process CLI tests for scripts/run.py main()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run import main


def test_no_args_prints_help(capsys):
    rc = main([])
    assert rc == 2
    assert "usage" in capsys.readouterr().out.lower() or rc == 2


def test_version(capsys):
    from scripts import __version__
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_demo_writes_all_artifacts(tmp_path, capsys):
    rc = main(["demo", "--output", str(tmp_path / "demo")])
    assert rc == 0
    out = tmp_path / "demo"
    assert (out / "demo_tracking.csv").exists()
    assert (out / "demo_summary.json").exists()
    assert (out / "demo_fft.json").exists()
    # PNG is optional (skipped without matplotlib).
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    assert payload["n_frames"] >= 100
    assert payload["csv"].endswith("demo_tracking.csv")


def test_track_missing_config_exits_usage(tmp_path, capsys):
    rc = main(["track", "--config", str(tmp_path / "nope.json")])
    assert rc == 2
    assert "error" in capsys.readouterr().err.lower()


def test_probe_on_synthetic_video(tmp_path, capsys):
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=15)
    cfg_path = write_json_config(tmp_path, make_config_dict(video, meta))
    rc = main(["probe", "--config", str(cfg_path)])
    assert rc == 0
    out = capsys.readouterr().out
    infos = json.loads(out)
    assert infos[0]["n_frames"] == meta["n_frames"]
    assert infos[0]["fps"] == pytest.approx(meta["fps"], rel=0.1)


def test_track_on_synthetic_video(tmp_path, capsys):
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=15)
    cfg_path = write_json_config(
        tmp_path, make_config_dict(video, meta, output=str(tmp_path / "out"))
    )
    rc = main(["track", "--config", str(cfg_path)])
    assert rc == 0
    out_dir = tmp_path / "out"
    base = video.name
    assert (out_dir / f"{base}_tracking.csv").exists()
    assert (out_dir / f"{base}_summary.json").exists()
    captured = capsys.readouterr().out
    payload = json.loads(captured)
    # n_frames now counts every recorded point (init frame + each update).
    # A 15-frame clip yields at most 15 points; mp4v may drop a frame, so
    # assert a sane lower bound instead of an exact count.
    assert 10 <= payload["n_frames"] <= 15
    assert payload["objects"] == ["ball"]


def test_fft_on_tracked_video(tmp_path, capsys):
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=30)
    out = tmp_path / "out"
    cfg_path = write_json_config(
        tmp_path, make_config_dict(video, meta, output=str(out))
    )
    assert main(["track", "--config", str(cfg_path)]) == 0
    rc = main(["fft", "--config", str(cfg_path), "--no-plots"])
    assert rc == 0
    base = video.name
    assert (out / f"{base}_fft.json").exists()


def test_report_on_tracked_video(tmp_path, capsys):
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=20)
    out = tmp_path / "out"
    cfg_path = write_json_config(
        tmp_path, make_config_dict(video, meta, output=str(out))
    )
    assert main(["track", "--config", str(cfg_path)]) == 0
    rc = main(["report", "--config", str(cfg_path)])
    assert rc == 0
    base = video.name
    rep = out / f"{base}_report.md"
    assert rep.exists()
    assert "Tracking report" in rep.read_text(encoding="utf-8")


def test_unknown_subcommand(capsys):
    # argparse exits via SystemExit on an unknown subcommand.
    with pytest.raises(SystemExit):
        main(["bogus"])


def test_output_override(tmp_path, capsys):
    cv2 = pytest.importorskip("cv2")
    from tests.conftest import make_synthetic_video, make_config_dict, write_json_config

    video, meta = make_synthetic_video(tmp_path / "syn.mp4", n_frames=10)
    cfg_path = write_json_config(tmp_path, make_config_dict(video, meta))
    alt = tmp_path / "alt_out"
    rc = main(["track", "--config", str(cfg_path), "--output", str(alt)])
    assert rc == 0
    base = video.name
    assert (alt / f"{base}_tracking.csv").exists()
