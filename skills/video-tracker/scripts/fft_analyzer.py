"""FFT spectrum analysis of tracked 1-D coordinate signals.

Given a coordinate time series (x_px, y_px, or a cm-scaled variant) and the
sampling FPS, compute the amplitude spectrum (normalized DFT magnitude),
extract the dominant positive-frequency peak, its period, and optional
spectral / trajectory figures. Pure numpy so it runs without OpenCV.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from .errors import FFTError


@dataclass
class SpectrumResult:
    """Outcome of one FFT analysis on a 1-D signal."""

    signal_name: str
    n_samples: int
    fps: float
    freqs: np.ndarray = field(repr=False, default=None)
    amplitudes: np.ndarray = field(repr=False, default=None)
    dominant_freq: float = 0.0
    dominant_amp: float = 0.0
    period_s: float | None = None
    top_peaks: list[tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "signal": self.signal_name,
            "n_samples": self.n_samples,
            "fps": self.fps,
            "dominant_freq_hz": round(float(self.dominant_freq), 6),
            "dominant_amplitude": round(float(self.dominant_amp), 6),
            "period_s": (
                None if self.period_s is None else round(float(self.period_s), 6)
            ),
        "top_peaks": [
            {"freq_hz": round(f, 6), "amplitude": round(a, 6)}
            for f, a in self.top_peaks
        ],
    }


@dataclass
class ObjectAnalysis:
    """FFT analysis of one tracked object's x and y coordinate series.

    Carries the raw :class:`SpectrumResult` objects (used for plotting) plus a
    reduced ``to_dict()`` form (used for the JSON / report). Replaces the
    fragile double-computation that the CLI previously did to rebuild spectra
    from the reduced dict.
    """

    name: str
    fps: float
    scale_cm_per_px: float | None
    x: "SpectrumResult"
    y: "SpectrumResult"
    x_cm: "SpectrumResult | None" = None
    y_cm: "SpectrumResult | None" = None

    def to_dict(self) -> dict:
        out: dict = {
            "object": self.name,
            "fps": self.fps,
            "scale_cm_per_px": self.scale_cm_per_px,
            "x": self.x.to_dict(),
            "y": self.y.to_dict(),
        }
        if self.x_cm is not None and self.y_cm is not None:
            out["x_cm"] = self.x_cm.to_dict()
            out["y_cm"] = self.y_cm.to_dict()
        return out


def compute_spectrum(
    signal: Sequence[float],
    fps: float,
    name: str = "signal",
    max_freq: float | None = None,
    top_peaks: int = 5,
) -> SpectrumResult:
    """FFT amplitude spectrum of *signal* sampled at *fps* Hz.

    The magnitude is normalized by ``N/2`` so a sinusoid of amplitude A
    yields a peak of roughly A. The zero-frequency (DC) bin is ignored
    when searching for the dominant peak. If *max_freq* is given, only
    frequencies up to that value (one-sided) are considered.
    """
    s = np.asarray(signal, dtype=np.float64)
    if s.ndim != 1:
        raise FFTError(f"signal must be 1-D, got shape {s.shape}")
    if s.size < 2:
        raise FFTError(f"need at least 2 samples, got {s.size}")
    if fps <= 0:
        raise FFTError(f"fps must be > 0, got {fps}")

    n = s.size
    fft_vals = np.fft.rfft(s) if n % 2 == 0 else np.fft.fft(s)
    if n % 2 == 0:
        freqs = np.fft.rfftfreq(n, d=1.0 / fps)
        amps = np.abs(fft_vals) * 2.0 / n
    else:
        keep = np.arange(n // 2 + 1)
        freqs = np.fft.fftfreq(n, d=1.0 / fps)[keep]
        amps = np.abs(fft_vals)[keep] * 2.0 / n

    if max_freq is not None and max_freq > 0:
        m = freqs <= max_freq
        freqs, amps = freqs[m], amps[m]

    # Dominant peak, skipping DC.
    if freqs.size >= 2:
        i = int(np.argmax(amps[1:])) + 1
        dominant_freq = float(freqs[i])
        dominant_amp = float(amps[i])
    else:
        dominant_freq = 0.0
        dominant_amp = float(amps[0]) if amps.size else 0.0
    period = None if dominant_freq <= 0 else 1.0 / dominant_freq

    # Top-N peaks by amplitude (excluding DC), descending.
    if freqs.size >= 2:
        order = np.argsort(amps[1:])[::-1][:max(1, top_peaks)] + 1
        top = [
            (float(freqs[j]), float(amps[j]))
            for j in order
            if float(freqs[j]) > 0
        ]
    else:
        top = []

    return SpectrumResult(
        signal_name=name,
        n_samples=int(s.size),
        fps=float(fps),
        freqs=freqs,
        amplitudes=amps,
        dominant_freq=dominant_freq,
        dominant_amp=dominant_amp,
        period_s=period,
        top_peaks=top,
    )


def analyze_object(
    points,
    name: str,
    fps: float,
    scale: float | None = None,
    max_freq: float | None = None,
    top_peaks: int = 5,
) -> dict:
    """FFT-analyze a tracked object's x and y coordinate series.

    *points* is a sequence of :class:`TrajectoryPoint`-like objects with
    ``x_px`` / ``y_px`` / ``time_s`` attributes. Returns::

        {"object": name, "fps": fps, "scale_cm_per_px": scale,
         "x": {...}, "y": {...}, ["x_cm": {...}, "y_cm": {...}]}

    each ``"..."`` entry being the reduced dict of a
    :class:`SpectrumResult`.
    """
    if not points:
        raise FFTError(f"object {name!r} has no tracked frames")
    x_px = np.array([p.x_px for p in points], dtype=np.float64)
    y_px = np.array([p.y_px for p in points], dtype=np.float64)

    out: dict = {
        "object": name,
        "fps": float(fps),
        "scale_cm_per_px": scale,
    }
    sx = compute_spectrum(x_px, fps, f"{name}.x_px", max_freq, top_peaks)
    sy = compute_spectrum(y_px, fps, f"{name}.y_px", max_freq, top_peaks)
    sx_cm = sy_cm = None
    if scale is not None:
        sx_cm = compute_spectrum(x_px * scale, fps, f"{name}.x_cm",
                                 max_freq, top_peaks)
        sy_cm = compute_spectrum(y_px * scale, fps, f"{name}.y_cm",
                                 max_freq, top_peaks)
    return ObjectAnalysis(name, float(fps), scale, sx, sy, sx_cm, sy_cm)


def write_spectra(
    results: list["SpectrumResult"],
    json_path: Path,
    png_path: Path | None = None,
    trajectories: dict[str, tuple[list[float], list[float]]] | None = None,
) -> tuple[Path, Path | None]:
    """Write the FFT report: JSON (always) + PNG figures (optional).

    The JSON holds one reduced entry per analysed signal. When *png_path*
    is given, a matplotlib (Agg) figure is saved: one row per signal with
    its amplitude spectrum and the dominant peak marked; when
    *trajectories* (``{label: (xs, ys)}``) is given, trajectory overlays
    are appended as extra panels.
    """
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_signals": len(results),
        "signals": [r.to_dict() for r in results],
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    if png_path is None:
        return json_path, None
    png_path = Path(png_path)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - matplotlib optional
        return json_path, None

    n_spectra = len(results)
    n_traj = len(trajectories) if trajectories else 0
    n = max(1, n_spectra + n_traj)
    fig, axes = plt.subplots(n, 1, figsize=(10, 3 * n),
                             layout="constrained", squeeze=False)
    ax_i = 0
    for spec in results:
        ax = axes[ax_i][0]
        ax_i += 1
        ax.semilogy(spec.freqs, spec.amplitudes, lw=0.8)
        ax.axvline(
            spec.dominant_freq, color="crimson", lw=1, ls="--",
            label=f"dominant {spec.dominant_freq:.3f} Hz",
        )
        ax.set_title(f"{spec.signal_name}", fontsize=10)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Amplitude")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    if trajectories:
        for label, (xs, ys) in trajectories.items():
            ax = axes[ax_i][0]
            ax_i += 1
            ax.plot(xs, ys, lw=0.8)
            ax.set_aspect("equal")
            ax.set_title(f"{label} trajectory", fontsize=10)
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            ax.grid(True, alpha=0.3)
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return json_path, png_path
