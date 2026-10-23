"""video-tracker acceptance: FFT correctness + physics consistency probes."""
from __future__ import annotations

import math

from conftest import run_in_skill

FFT_SINE = """
import json, math, sys
sys.path.insert(0, "skills/video-tracker")
from scripts.fft_analyzer import compute_spectrum
fps, f, amp, n = 30.0, 2.0, 5.0, 300
signal = [amp * math.sin(2 * math.pi * f * i / fps) for i in range(n)]
res = compute_spectrum(signal, fps, name="x")
print(json.dumps({"dominant_freq": res.dominant_freq,
                  "dominant_amp": res.dominant_amp,
                  "period_s": res.period_s,
                  "n_peaks": len(res.top_peaks)}))
"""

FFT_TWO_TONE = """
import json, math, sys
sys.path.insert(0, "skills/video-tracker")
from scripts.fft_analyzer import compute_spectrum
fps, n = 50.0, 500
signal = [3.0 * math.sin(2 * math.pi * 1.5 * i / fps)
          + 1.0 * math.sin(2 * math.pi * 4.0 * i / fps) for i in range(n)]
res = compute_spectrum(signal, fps, name="x", top_peaks=3)
peaks = sorted(round(f, 2) for f, a in res.top_peaks
               if a > 0.25 * res.dominant_amp)
print(json.dumps({"dominant_freq": round(res.dominant_freq, 3),
                  "dominant_amp": round(res.dominant_amp, 3),
                  "peaks": peaks}))
"""

PHYSICS_SMOOTH = """
import json, math, sys
sys.path.insert(0, "skills/video-tracker")
from scripts.physics import teleport_metric
fps, n = 30.0, 120
x = [10.0 * math.sin(2 * math.pi * 1.0 * i / fps) for i in range(n)]
y = [10.0 * math.cos(2 * math.pi * 1.0 * i / fps) for i in range(n)]
m = teleport_metric(x, y, 1.0 / fps)
print(json.dumps({"max_step_px": m.get("max_step_px"),
                  "median_step_px": m.get("median_step_px"),
                  "frac_outlier": m.get("frac_outlier"),
                  "n_teleport": m.get("n_teleport")}))
"""


def test_fft_recovers_sine_frequency_and_amplitude():
    out = run_in_skill("video-tracker", FFT_SINE)
    assert abs(out["dominant_freq"] - 2.0) < 0.05, out
    assert abs(out["dominant_amp"] - 5.0) < 0.3, out
    assert abs(out["period_s"] - 0.5) < 0.02, out
    assert out["n_peaks"] >= 1


def test_fft_two_tone_spectrum_has_two_peaks():
    out = run_in_skill("video-tracker", FFT_TWO_TONE)
    assert abs(out["dominant_freq"] - 1.5) < 0.05, out
    assert abs(out["dominant_amp"] - 3.0) < 0.3, out
    assert 4.0 in out["peaks"], f"missing 4 Hz component: {out}"
    assert len(out["peaks"]) == 2, out


def test_physics_probe_flags_no_teleport_on_smooth_track():
    out = run_in_skill("video-tracker", PHYSICS_SMOOTH)
    # a smooth circular track has small, uniform steps and zero teleports
    assert out["n_teleport"] == 0, out
    assert out["frac_outlier"] < 0.05, out
    # max step stays well below the tracking-window teleport cap
    assert out["max_step_px"] < 50.0, out
