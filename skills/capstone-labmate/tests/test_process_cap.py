"""Unit tests for stage C (downsample + fit + stats + plot degradation).

These exercise the pure-python data transforms in process_cap.py without
needing a real .cap, by calling the module-level functions directly.
"""
import json
import math
import struct
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import process_cap  # noqa: E402


# ---------------------------------------------------------------- downsample
def test_downsample_small_series_keeps_all() -> None:
    # n <= target -> keep every point verbatim
    kept, feats = process_cap._downsample([0, 1, 2], [10, 20, 30], 10)
    assert kept == [0, 1, 2]
    assert [f["kind"] for f in feats] == ["point", "point", "point"]
    assert [f["v"] for f in feats] == [10, 20, 30]


def test_downsample_respects_target_and_extremes() -> None:
    # 100 points down to target=10: result should be <= ~12 features
    t = [i for i in range(100)]
    # inject a global peak at index 77 and a global valley at index 13
    v = [math.sin(i * 0.1) for i in range(100)]
    v[77] = 1e6
    v[13] = -1e6
    kept, feats = process_cap._downsample(t, v, 10)
    assert len(feats) <= 12  # 10 segment means + up to 2 extremes
    
    kinds = [f["kind"] for f in feats]
    assert "peak" in kinds
    assert "valley" in kinds
    
    # the extreme features must carry the correct raw index
    peak = next(f for f in feats if f["kind"] == "peak")
    valley = next(f for f in feats if f["kind"] == "valley")
    assert peak["i"] == 77
    assert valley["i"] == 13


def test_downsample_empty() -> None:
    kept, feats = process_cap._downsample([], [], 10)
    assert kept == [] and feats == []


def test_downsample_target_clamped_to_at_least_2() -> None:
    kept, feats = process_cap._downsample([0, 1, 2, 3, 4, 5],
                                          [1, 2, 3, 4, 5, 6], 1)
    # target clamped to 2 (min 2); the loop produces at most ~3 feats
    assert len(feats) <= 4


# -------------------------------------------------------------------- linfit
def test_linfit_exact_line() -> None:
    # v = 2*t + 3 exactly -> slope=2, intercept=3, r^2=1
    t = [0.0, 1.0, 2.0, 3.0, 4.0]
    v = [3.0, 5.0, 7.0, 9.0, 11.0]
    fit = process_cap._linfit(t, v)
    assert abs(fit["slope"] - 2.0) < 1e-9
    assert abs(fit["intercept"] - 3.0) < 1e-9
    assert abs(fit["r_squared"] - 1.0) < 1e-9


def test_linfit_too_few_points() -> None:
    fit = process_cap._linfit([0.0], [5.0])
    assert fit["slope"] == 0.0
    assert fit["intercept"] == 5.0
    assert fit["r_squared"] is None


def test_linfit_constant_series_r2_none() -> None:
    # constant v -> syy=0 -> r^2 undefined -> None
    fit = process_cap._linfit([0.0, 1.0, 2.0], [5.0, 5.0, 5.0])
    assert fit["r_squared"] is None
    assert abs(fit["intercept"] - 5.0) < 1e-9


# --------------------------------------------------------------------- stats
def test_stats_known_values() -> None:
    s = process_cap._stats([1.0, 2.0, 3.0, 4.0])
    assert s["mean"] == 2.5
    assert s["min"] == 1.0
    assert s["max"] == 4.0
    # population std of [1,2,3,4] = sqrt(1.25)
    assert abs(s["std"] - math.sqrt(1.25)) < 1e-9


def test_stats_single_value_std_zero() -> None:
    s = process_cap._stats([7.0])
    assert s["mean"] == 7.0
    assert s["std"] == 0.0


def test_stats_empty() -> None:
    s = process_cap._stats([])
    assert s == {"mean": None, "min": None, "max": None, "std": None}


# ------------------------------------------------------------- plot degrade
def test_try_plot_degrades_without_matplotlib(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-04: when matplotlib is unavailable _try_plot returns False, not crash."""
    import builtins
    real_import = builtins.__import__

    def _broken_import(name: str, *a, **k):
        if name.startswith("matplotlib"):
            raise ImportError("matplotlib deliberately blocked in test")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _broken_import)
    
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ok = process_cap._try_plot(Path(d), "series X", [0, 1, 2], [1, 2, 3], [])
        assert ok is False


def test_safe_filename_sanitizes_label() -> None:
    # Aligned with the refactored function name in process_cap.py
    assert process_cap._safe_filename("Series A/b c") == "Series_A_b_c"


# ------------------------------------------------------------------- csv export
def test_write_csv_roundtrip(tmp_path: Path) -> None:
    """R-05 support: full (t, v) export for Excel screening of weak peaks."""
    p = process_cap._write_csv(tmp_path / "csv", "s 1",
                               [0.0, 0.05, 0.1], [1.0, 2.0, 3.0])
    assert p.name == "s_1.csv"
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "time_s,value"
    assert lines[1] == "0,1"
    assert lines[3] == "0.1,3"
    assert len(lines) == 4


# ---------------------------------------------------------------- run()
def test_run_on_bad_input_returns_1(tmp_path: Path) -> None:
    bad = tmp_path / "not_a_cap.txt"
    bad.write_text("hello")
    assert process_cap.run(bad, 50, tmp_path / "work") == 1


def test_run_full_pipeline_with_fake_cap(tmp_path: Path) -> None:
    """Build a minimal valid .cap, run stage C, check artifacts exist."""
    cap = tmp_path / "rec.cap"
    n = 60
    values = [float(i) for i in range(n)]
    blob = b"".join(struct.pack("<iif", 1, 0, v) for v in values)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Experiment>\n'
        '<Measurement EUID="e1" Name="TestSensor" BaseUnit="0"/>\n'
        '<DataRepository>\n'
        f' <DataSet Name="s1" DataSetID="id1" DataCacheDataSize="{n}">\n'
        f'  <DependentStorageElement FileName="data/Z_test.tmp" '
        f'DataCacheDataSize="{n}" DataOffsetValue="0" StorageType="0"/>\n'
        f'  <IndependentStorageElement IntervalCacheStartValue="0.0" '
        f'IntervalCacheInterval="0.05" CacheDataCount="{n}" StorageType="1"/>\n'
        f' </DataSet>\n'
        '</DataRepository>\n'
        '</Experiment>\n'
    )
    with zipfile.ZipFile(cap, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.xml", xml)
        zf.writestr("data/Z_test.tmp", blob)

    rc = process_cap.run(cap, 20, tmp_path / "work")
    assert rc == 0
    stage = (tmp_path / "work") / "stage_c"
    assert (stage / "summary.json").exists()
    assert (stage / "manifest.json").exists()
    
    csv_file = stage / "csv" / "s1.csv"
    assert csv_file.exists()
    csv_lines = csv_file.read_text(encoding="utf-8").strip().splitlines()
    assert csv_lines[0] == "time_s,value"
    assert len(csv_lines) == n + 1  # header + every raw point, no downsampling
    
    summary = json.loads((stage / "summary.json").read_text(encoding="utf-8"))
    assert len(summary) == 1
    assert summary[0]["series"] == "s1"
    assert summary[0]["raw_points"] == n
    # 20 target means + up to 2 extremes -> <= 22 feature points
    assert len(summary[0]["feature_points"]) <= 22
