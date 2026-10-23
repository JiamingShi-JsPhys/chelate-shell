"""Tests for the physics-consistency module and the ``physics`` CLI probe.

The probes are numpy-only: they ask whether a trajectory obeys Newtonian
laws (conservation of an invariant, equation-of-motion fit, smoothness)
rather than whether it matches a reference pixel-by-pixel. A faithful
reconstruction of the design motion scores ~1.0 on every probe; a corrupt,
swapped or gappy track degrades one or more of them.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from scripts.physics import (
    compare_trajectories,
    eom_dynamical_score,
    object_physics,
    score_trajectory,
    teleport_metric,
)
from scripts.errors import FFTError


def _uniform(n, fx, fy, cx=240.0, cy=240.0, amp=100.0, dt=1.0 / 60.0):
    t = np.arange(n) * dt

    def _wave(f):
        return np.zeros(n) if f is None else amp * np.sin(2 * math.pi * f * t)

    x = cx + _wave(fx)
    y = cy + _wave(fy)
    return x, y, dt


# --- probe: teleport -------------------------------------------------------- #
def test_teleport_clean_uniform_track_is_zero():
    x, y, dt = _uniform(60, 0.0, 0.0)
    x = np.arange(60) * 1.0  # constant step
    y = np.zeros(60)
    tele = teleport_metric(x, y, dt)
    assert tele["n_teleport"] == 0
    assert tele["abs_cap_hit"] is False


def test_teleport_flags_a_swap():
    x = np.concatenate([np.linspace(0, 50, 40), np.linspace(50, 0, 20)])
    y = np.zeros(60)
    # inject a large instantaneous jump in the middle
    x[29:31] += 200.0
    tele = teleport_metric(x, y, 1.0 / 60.0)
    assert tele["n_teleport"] >= 1
    assert tele["max_step_px"] > 100.0


def test_teleport_requires_min_frames():
    tele = teleport_metric([0, 1, 2], [0, 0, 0], 0.01)
    assert tele["n_teleport"] == 0
    assert tele["frac_outlier"] == 0.0


# --- probe: dynamical score ------------------------------------------------- #
def test_dynamical_score_perfect_sinusoid():
    x, y, dt = _uniform(240, 0.5, 0.5)
    s = eom_dynamical_score(x, y, dt, "lissajous", 0.5, 0.5)
    assert s > 0.99


def test_dynamical_score_flat_axis_is_perfect():
    # one stationary axis must not drag the two-axis score down
    x = 240.0 + np.zeros(240)
    y, _, dt = _uniform(240, 0.5, 0.5)
    s = eom_dynamical_score(x, y, dt, "harmonic", 0.5, None)
    assert s > 0.99


def test_dynamical_score_rejects_wrong_frequency():
    x, y, dt = _uniform(240, 0.5, 0.5)
    # fit against a frequency the motion does not have
    s = eom_dynamical_score(x, y, dt, "lissajous", 0.9, 0.9)
    assert s < 0.5


def test_dynamical_score_linear():
    t = np.arange(180) * (1.0 / 60.0)
    x = 240.0 + 40.0 * t
    y = 240.0 + 10.0 * t
    s = eom_dynamical_score(x, y, 1.0 / 60.0, "linear", None, None)
    assert s > 0.99


# --- probe: conservation ---------------------------------------------------- #
def test_conservation_uniform_ke_is_high():
    t = np.arange(240) * (1.0 / 60.0)
    x = 240.0 + 40.0 * t
    y = 240.0 + 10.0 * t
    s, inv, _ = _conservation(x, y, 1.0 / 60.0, "linear")
    assert inv == "kinetic_energy"
    assert s > 0.95


def _conservation(x, y, dt, fam, fx=None, fy=None, center=None):
    from scripts.physics import conservation_score
    return conservation_score(x, y, dt, fam, fx, fy, center)


def test_conservation_sho_energy_high():
    x, y, dt = _uniform(300, 0.5, None)
    s, inv, _ = _conservation(x, y, dt, "harmonic", 0.5, None, center=(240.0, 240.0))
    assert inv == "sho_energy_x"
    assert s > 0.9


def test_conservation_spiral_radial_speed_high():
    n = 300
    dt = 1.0 / 60.0
    t = np.arange(n) * dt
    omega = 2 * math.pi * 0.5
    r = 20.0 + 25.0 * t
    x = 240.0 + r * np.cos(omega * t)
    y = 240.0 + r * np.sin(omega * t)
    s, inv, _ = _conservation(x, y, dt, "spiral", 0.5, 0.5, center=(240.0, 240.0))
    assert inv == "radial_linearity"
    assert s > 0.9


def test_conservation_damped_decay_linearity_high():
    n = 300
    dt = 1.0 / 60.0
    t = np.arange(n) * dt
    x = 240.0 + 150.0 * np.exp(-0.4 * t) * np.sin(2 * math.pi * 0.6 * t)
    y = 240.0 + np.zeros(n)
    s, inv, _ = _conservation(x, y, dt, "damped", 0.6, None, center=(240.0, 240.0))
    assert inv == "decay_linearity"
    assert s > 0.85


def test_conservation_unknown_family_is_nan():
    s, inv, _ = _conservation([1, 2, 3, 4], [1, 2, 3, 4], 1.0, "unknown")
    assert math.isnan(s)
    assert inv == "unknown"


# --- score_trajectory / compare -------------------------------------------- #
def test_score_trajectory_returns_full_report():
    x, y, dt = _uniform(300, 0.5, 0.5)
    rep = score_trajectory(x, y, dt, "lissajous", 0.5, 0.5, center=(240.0, 240.0))
    for key in ("family", "invariant", "conservation_score",
                "invariant_value", "dynamical_score", "teleport"):
        assert key in rep
    assert rep["conservation_score"] > 0.9
    assert rep["dynamical_score"] > 0.99


def test_score_trajectory_rejects_bad_dt():
    x, y, dt = _uniform(60, 0.5, 0.5)
    with pytest.raises(FFTError):
        score_trajectory(x, y, 0.0, "linear")


def test_compare_trajectories_delta_zero_when_identical():
    x, y, dt = _uniform(300, 0.5, 0.5)
    rep = compare_trajectories(x, y, x, y, dt, "lissajous", 0.5, 0.5,
                              center=(240.0, 240.0))
    assert abs(rep["delta_conservation"]) < 1e-9
    assert abs(rep["delta_dynamical"]) < 1e-9


def test_compare_trajectories_penalises_a_swap():
    x, y, dt = _uniform(300, 0.5, 0.5)
    # candidate has a big jump injected (as a tracker swap would look)
    cx = x.copy()
    cx[140:150] += 150.0
    rep = compare_trajectories(cx, y, x, y, dt, "lissajous", 0.5, 0.5,
                              center=(240.0, 240.0))
    assert rep["delta_conservation"] < 0.0 or rep["delta_dynamical"] < 0.0


# --- object_physics (ObjectResult) ----------------------------------------- #
def test_object_physics_accepts_object_result():
    import numpy as np
    from scripts.tracker import ObjectResult, TrajectoryPoint
    from scripts.config import ObjectROI

    t = np.arange(300) * (1.0 / 60.0)
    # genuine circular motion: x on cos, y on sin (quadrature phase)
    x = 240.0 + 100.0 * np.cos(2 * math.pi * 0.5 * t)
    y = 240.0 + 100.0 * np.sin(2 * math.pi * 0.5 * t)
    pts = [TrajectoryPoint(i, float(ti), float(xi), float(yi), 1.0, False)
           for i, (ti, xi, yi) in enumerate(zip(t, x, y))]
    res = ObjectResult(name="ball",
                      roi=ObjectROI("ball", 0, 0, 1, 1),
                      points=pts)
    report = object_physics(res, 1.0 / 60.0, "circular", 0.5, 0.5,
                           center=(240.0, 240.0))
    assert report.family == "circular"
    assert report.conservation_score > 0.9
    assert report.dynamical_score > 0.99
    assert "conservation_score" in report.to_dict()


def test_object_physics_requires_four_points():
    from scripts.tracker import ObjectResult, TrajectoryPoint
    from scripts.config import ObjectROI
    pts = [TrajectoryPoint(0, 0.0, 0.0, 0.0, 1.0, False)]
    res = ObjectResult(name="s", roi=ObjectROI("s", 0, 0, 1, 1), points=pts)
    with pytest.raises(FFTError):
        object_physics(res, 1.0, "linear")


# --- CLI wiring ------------------------------------------------------------- #
def test_run_module_exposes_physics_subcommand():
    from scripts import run
    p = run._build_parser()
    # parse a physics invocation (no execution)
    args = p.parse_args([
        "physics", "--config", "x.json", "--family", "linear",
    ])
    assert args.cmd == "physics"
    assert args.family == "linear"
    assert hasattr(run, "cmd_physics")
