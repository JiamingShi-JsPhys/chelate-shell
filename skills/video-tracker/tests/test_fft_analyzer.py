"""Tests for FFT spectrum analysis (pure numpy — always runs)."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.errors import FFTError
from scripts.fft_analyzer import (
    SpectrumResult,
    analyze_object,
    compute_spectrum,
    write_spectra,
)
from scripts.tracker import ObjectROI, TrajectoryPoint


def _points(xs, ys, fps=30.0):
    return [
        TrajectoryPoint(i, i / fps, float(x), float(y), 1.0, False)
        for i, (x, y) in enumerate(zip(xs, ys))
    ]


def test_compute_spectrum_sine_recoverable():
    fps = 30.0
    n = 300
    t = np.arange(n) / fps
    sig = 5.0 * np.sin(2 * np.pi * 1.5 * t)
    spec = compute_spectrum(sig, fps, "s")
    assert spec.dominant_freq == pytest.approx(1.5, abs=0.05)
    assert spec.dominant_amp == pytest.approx(5.0, abs=0.3)
    assert spec.period_s == pytest.approx(1 / 1.5, rel=0.05)


def test_compute_spectrum_odd_length():
    fps = 30.0
    n = 301  # odd, exercises the odd-length branch
    t = np.arange(n) / fps
    sig = np.sin(2 * np.pi * 2.0 * t)
    spec = compute_spectrum(sig, fps, "odd")
    assert spec.dominant_freq == pytest.approx(2.0, abs=0.05)
    assert spec.n_samples == n


def test_compute_spectrum_dc_skipped():
    # A constant signal has all energy at DC; dominant must come from
    # the (near-zero) positive-frequency bins, not the DC bin.
    spec = compute_spectrum([1.0, 1.0, 1.0, 1.0, 1.0], 10.0, "const")
    assert spec.dominant_freq >= 0.0
    # Amplitudes of non-DC bins are ~0.
    assert spec.dominant_amp < 1e-9


def test_compute_spectrum_max_freq_mask():
    fps = 100.0
    t = np.arange(100) / fps
    sig = np.sin(2 * np.pi * 1.0 * t) + np.sin(2 * np.pi * 40.0 * t)
    spec_full = compute_spectrum(sig, fps, "full")
    spec_masked = compute_spectrum(sig, fps, "masked", max_freq=5.0)
    # The 40 Hz component must be excluded by the mask.
    assert spec_masked.dominant_freq == pytest.approx(1.0, abs=0.2)
    assert spec_full.dominant_freq in (1.0, 40.0)


def test_compute_spectrum_top_peaks():
    fps = 50.0
    t = np.arange(500) / fps
    sig = np.sin(2 * np.pi * 1.0 * t) + 2.0 * np.sin(2 * np.pi * 3.0 * t)
    spec = compute_spectrum(sig, fps, "multi", top_peaks=3)
    freqs = [f for f, _ in spec.top_peaks]
    assert any(abs(f - 3.0) < 0.1 for f in freqs)
    assert len(spec.top_peaks) <= 3


def test_compute_spectrum_too_short():
    with pytest.raises(FFTError):
        compute_spectrum([1.0], 10.0, "tiny")


def test_compute_spectrum_bad_fps():
    with pytest.raises(FFTError):
        compute_spectrum([1.0, 2.0, 3.0], 0.0, "bad")


def test_compute_spectrum_2d_rejected():
    with pytest.raises(FFTError):
        compute_spectrum(np.ones((2, 2)), 10.0, "2d")


def test_analyze_object_px_and_cm():
    n = 240
    fps = 30.0
    t = np.arange(n) / fps
    xs = 100 * np.sin(2 * np.pi * 0.5 * t)
    ys = np.zeros(n)
    pts = _points(xs, ys, fps)
    out = analyze_object(pts, "ball", fps, scale=0.1, max_freq=None,
                         top_peaks=3).to_dict()
    assert out["object"] == "ball"
    assert out["scale_cm_per_px"] == 0.1
    for key in ("x", "y", "x_cm", "y_cm"):
        assert key in out
    assert out["x"]["dominant_freq_hz"] == pytest.approx(0.5, abs=0.05)
    # cm variant is px * 0.1 -> same frequency, 0.1x amplitude.
    assert out["x_cm"]["dominant_amplitude"] == pytest.approx(
        out["x"]["dominant_amplitude"] * 0.1, rel=0.05
    )


def test_analyze_object_no_points():
    with pytest.raises(FFTError):
        analyze_object([], "empty", 30.0)


def test_spectrum_result_to_dict():
    s = SpectrumResult("sig", 100, 30.0,
                       freqs=np.array([0.0, 1.0, 2.0]),
                       amplitudes=np.array([0.0, 1.0, 0.5]),
                       dominant_freq=1.0, dominant_amp=1.0, period_s=1.0,
                       top_peaks=[(1.0, 1.0), (2.0, 0.5)])
    d = s.to_dict()
    assert d["signal"] == "sig"
    assert d["n_samples"] == 100
    assert d["dominant_freq_hz"] == 1.0
    assert d["period_s"] == 1.0
    assert d["top_peaks"][0] == {"freq_hz": 1.0, "amplitude": 1.0}


def test_write_spectra_json_only(tmp_path):
    fps = 30.0
    t = np.arange(300) / fps
    specs = [
        compute_spectrum(np.sin(2 * np.pi * 1.0 * t), fps, "a"),
        compute_spectrum(np.sin(2 * np.pi * 2.0 * t), fps, "b"),
    ]
    jp, png = write_spectra(specs, tmp_path / "f.json", None)
    assert jp.exists() and not png
    import json

    data = json.loads(jp.read_text(encoding="utf-8"))
    assert data["n_signals"] == 2
    assert data["signals"][0]["signal"] == "a"


def test_write_spectra_with_png(tmp_path):
    pytest.importorskip("matplotlib")
    fps = 30.0
    t = np.arange(300) / fps
    specs = [compute_spectrum(np.sin(2 * np.pi * 1.0 * t), fps, "a")]
    jp, png = write_spectra(
        specs,
        tmp_path / "f.json",
        tmp_path / "f.png",
        trajectories={"a": ([0.0, 1.0], [0.0, 1.0])},
    )
    assert jp.exists() and png and png.exists()


def test_write_spectra_no_matplotlib(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake(name, *a, **kw):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("no mpl")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    fps = 30.0
    t = np.arange(100) / fps
    specs = [compute_spectrum(np.sin(2 * np.pi * 1.0 * t), fps, "a")]
    jp, png = write_spectra(specs, tmp_path / "f.json", tmp_path / "f.png")
    assert jp.exists() and png is None  # PNG skipped, JSON still written
