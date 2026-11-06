"""Unit tests for the shared .cap parsing engine (net-room, stdlib only)."""

import io
import math
import struct
import zipfile
from pathlib import Path

import pytest

import _capx


def _make_cap(path: Path, n_points: int = 10, start: float = 0.0,
              interval: float = 0.05) -> Path:
    """Build a minimal valid .cap zip with one DataSet + one 12-byte tmp."""
    values = [float(i) for i in range(n_points)]
    blob = bytearray()
    for v in values:
        blob += struct.pack("<iif", 1, 0, v)

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Experiment>\n'
        f'<Measurement EUID="e1" Name="TestSensor" BaseUnit="0"/>\n'
        '<DataRepository>\n'
        f' <DataSet Name="s1" DataSetID="id1" DataCacheDataSize="{n_points}">\n'
        f'  <DependentStorageElement FileName="data/Z_test.tmp" '
        f'DataCacheDataSize="{n_points}" DataOffsetValue="0" StorageType="0"/>\n'
        f'  <IndependentStorageElement IntervalCacheStartValue="{start}" '
        f'IntervalCacheInterval="{interval}" CacheDataCount="{n_points}" '
        f'StorageType="1"/>\n'
        f' </DataSet>\n'
        '</DataRepository>\n'
        '</Experiment>\n'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.xml", xml)
        zf.writestr("data/Z_test.tmp", bytes(blob))
    return path


def test_is_zip_true(tmp_path: Path) -> None:
    p = _make_cap(tmp_path / "a.cap")
    assert _capx.is_zip(p) is True


def test_not_zip(tmp_path: Path) -> None:
    p = tmp_path / "b.txt"
    p.write_text("hello")
    assert _capx.is_zip(p) is False


def test_open_cap_zip_missing_main(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / "c.cap", "w") as zf:
        zf.writestr("foo.txt", "x")
    
    # Modern pytest exception assertion
    with pytest.raises(ValueError, match="entry not found"):
        _capx.open_cap_zip(tmp_path / "c.cap")


def test_read_tmp_values_and_gate(tmp_path: Path) -> None:
    p = _make_cap(tmp_path / "d.cap", n_points=5)
    zf = _capx.open_cap_zip(p)
    vals = _capx.read_tmp_values(zf, "data/Z_test.tmp", 5)
    assert vals == [0.0, 1.0, 2.0, 3.0, 4.0]
    
    # Validity gate: wrong expected count raises.
    with pytest.raises(ValueError, match="Diagnostic: do not continue"):
        _capx.read_tmp_values(zf, "data/Z_test.tmp", 99)


def test_time_axis_generation() -> None:
    # start + k*interval is computed in float; compare with tolerance
    # (0.05*3 = 0.15000000000000002 in double precision — that is the
    # faithful axis and must NOT be rounded away).
    axis = _capx.build_time_axis(0.0, 0.05, 4)
    expected = [0.0, 0.05, 0.10, 0.15]
    
    assert len(axis) == 4
    for a, e in zip(axis, expected):
        assert math.isclose(a, e, rel_tol=0, abs_tol=1e-12)


def test_extract_datasets(tmp_path: Path) -> None:
    p = _make_cap(tmp_path / "e.cap")
    zf = _capx.open_cap_zip(p)
    ds = _capx.extract_datasets(zf)
    
    assert len(ds) == 1
    assert ds[0].dataset_name == "s1"
    assert ds[0].data_cache_size == 10


def test_record_layout_constants() -> None:
    # Verify the hardcoded F4 constants match the expected 12-byte layout.
    assert _capx.RECORD_BYTES == 12
    assert _capx.RECORD_STRUCT == "<iif"
    
    # Verify packing logic yields exactly 12 bytes per record
    raw = struct.pack(_capx.RECORD_STRUCT, 1, 0, 7.5)
    assert len(raw) == 12
