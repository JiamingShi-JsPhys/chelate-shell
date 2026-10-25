"""Physics-consistency checks for tracked trajectories.

An optional, purely numerical companion to the FFT analysis: it asks
whether an extracted trajectory *obeys Newtonian physics*, not only
whether it matches a reference path. Three independent probes:

* **Teleport / smoothness** — a physical trajectory has bounded, smoothly
  varying speed; a tracker that silently swaps to the wrong object (or a
  gap in the recording) produces an instantaneous jump that is flagged here.
* **Conservation** — the motion's appropriate invariant (kinetic energy for
  constant-speed motion, simple-harmonic-oscillator energy for oscillators,
  angular speed for rotation, radial speed for an expanding spiral, decay
  linearity for a damped oscillator) is measured; its relative variance is
  the *invariant value*. A faithful track keeps it; a broken one does not.
* **Equation-of-motion fit** — the trajectory is fitted to the design model
  (sinusoid / damped sinusoid / polynomial / spiral) and the *dynamical
  score* is reported as ``1 - min(NMSE, 1)``.

The module is numpy-only (no OpenCV, no matplotlib, no torch) and operates
on plain arrays or the skill's own :class:`~.tracker.ObjectResult`, so it
adds no dependency to the lightweight tracker and can run on CPU alone.

All scoring functions take the *raw* extracted position series plus the
design parameters (frequencies, equilibrium centres, motion family). A
trajectory that is faithful to the design keeps every probe near its ideal
value; a corrupt / swapped / gappy track shows up as a degraded score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .errors import FFTError

# Relative-variance tolerance: below this the invariant counts as conserved.
_TOL_CV = 0.05
# Outlier multiplier on the robust (MAD) scale for the teleport probe.
_TELEPORT_K = 5.0


# --- low-level helpers ------------------------------------------------------ #
def _central_diff(x: np.ndarray, dt: float) -> np.ndarray:
    """Velocity-like central differences; 2nd-order one-sided at the ends."""
    x = np.asarray(x, dtype=float)
    n = x.size
    if n < 2:
        return np.zeros_like(x)
    d = np.zeros_like(x)
    if n >= 3:
        d[1:-1] = (x[2:] - x[:-2]) / (2.0 * dt)
        d[0] = (-3.0 * x[0] + 4.0 * x[1] - x[2]) / (2.0 * dt)
        d[-1] = (3.0 * x[-1] - 4.0 * x[-2] + x[-3]) / (2.0 * dt)
    else:
        d[0] = (x[1] - x[0]) / dt
        d[1] = (x[1] - x[0]) / dt
    return d


def _cv(arr: np.ndarray) -> float:
    """Coefficient of variation; the reference is the mean magnitude, so a
    non-negative quantity such as energy is always measured against a
    positive scale even when its signed mean is near zero."""
    arr = np.asarray(arr, dtype=float)
    ref = float(np.mean(np.abs(arr))) + 1e-9
    return float(np.std(arr) / ref)


# --- probe 1: teleport / smoothness ----------------------------------------- #
def teleport_metric(x: Sequence[float], y: Sequence[float], dt: float) -> dict:
    """Detect non-physical instantaneous jumps between consecutive samples.

    A physically-plausible track has smoothly varying speed. A tracker that
    silently swaps to the wrong object (or a gap / re-acquire spike) leaves a
    single-frame speed jump. Two signals are combined:

    * **velocity-change spike** — the 2nd difference of the speed series,
      scored against a robust MAD threshold, so a constant-speed track yields
      ~0 spikes.
    * **absolute cap** — any single step larger than 6× the median step and
      larger than 3 px.

    Returns a dict. A clean track gives ``n_teleport == 0``; a swap or gap
    shows up as a large value here even when the per-frame RMSE is modest.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 4:
        return {"frac_outlier": 0.0, "max_step_px": 0.0,
                "n_teleport": 0, "n_change_spike": 0, "abs_cap_hit": False,
                "median_step_px": 0.0}
    steps = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2)
    med = float(np.median(steps))

    second = np.abs(np.diff(np.diff(steps)))
    if second.size:
        s_med = float(np.median(second))
        s_mad = float(np.median(np.abs(second - s_med)))
        thr = s_med + _TELEPORT_K * 1.4826 * s_mad
        n_change = int((second > thr).sum())
    else:
        n_change = 0
    abs_cap_hit = bool((steps.max() > 6.0 * med) and (steps.max() > 3.0))
    n_abs = int(abs_cap_hit)
    n_teleport = max(n_change, n_abs)

    return {
        "frac_outlier": float(min(1.0, n_teleport / max(1, steps.size))),
        "max_step_px": float(steps.max()),
        "n_teleport": int(n_teleport),
        "n_change_spike": int(n_change),
        "abs_cap_hit": abs_cap_hit,
        "median_step_px": med,
    }


# --- probe 2: conservation -------------------------------------------------- #
def _nmse(q: np.ndarray, q_fit: np.ndarray) -> float:
    q = np.asarray(q, dtype=float)
    var = float(np.var(q))
    if var < 1e-12:
        var = 1e-12
    return float(np.mean((q - np.asarray(q_fit, dtype=float)) ** 2) / var)


def fit_sinusoid(q, t, omega):
    """Least-squares fit ``q = a sin(wt) + b cos(wt) + c`` (w fixed)."""
    q = np.asarray(q, dtype=float)
    s = np.sin(omega * t)
    c = np.cos(omega * t)
    A = np.vstack([s, c, np.ones_like(t)]).T
    coef, *_ = np.linalg.lstsq(A, q, rcond=None)
    return A @ coef


def fit_poly2(q, t):
    A = np.vstack([t ** 2, t, np.ones_like(t)]).T
    coef, *_ = np.linalg.lstsq(A, np.asarray(q, dtype=float), rcond=None)
    return A @ coef


def fit_damped(q, t, omega, lam_grid=None):
    """Fit ``q = exp(-lam t)(a sin wt + b cos wt) + c``; lam is searched."""
    if lam_grid is None:
        lam_grid = np.linspace(0.05, 1.5, 30)
    q = np.asarray(q, dtype=float)
    best, best_lam = np.inf, None
    for lam in lam_grid:
        env = np.exp(-lam * t)
        A = np.vstack([env * np.sin(omega * t),
                       env * np.cos(omega * t),
                       np.ones_like(t)]).T
        coef, *_ = np.linalg.lstsq(A, q, rcond=None)
        val = _nmse(q, A @ coef)
        if val < best:
            best, best_lam = val, float(lam)
    return best, best_lam


def _coord_recon(q, t, freq, family, omega=0.0):
    """Smooth, noise-free reconstruction of one coordinate."""
    q = np.asarray(q, dtype=float)
    if freq is not None:
        if family == "damped":
            _, lam = fit_damped(q, t, omega)
            env = np.exp(-lam * t)
            A = np.vstack([env * np.sin(omega * t),
                           env * np.cos(omega * t),
                           np.ones_like(t)]).T
            coef, *_ = np.linalg.lstsq(A, q, rcond=None)
            return A @ coef
        return fit_sinusoid(q, t, 2.0 * np.pi * freq)
    return fit_poly2(q, t)


def _spiral_center(x, y):
    """Least-squares rotation centre, correct for a partial spiral/circle."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 3:
        return float(np.mean(x)), float(np.mean(y))
    D = np.stack([2.0 * (x - x[0]), 2.0 * (y - y[0])], axis=1)
    b = (x ** 2 + y ** 2) - (x[0] ** 2 + y[0] ** 2)
    try:
        sol, *_ = np.linalg.lstsq(D, b, rcond=None)
        return float(sol[0]), float(sol[1])
    except np.linalg.LinAlgError:
        return float(np.mean(x)), float(np.mean(y))


def fit_spiral_recon(x, y, t, omega):
    """Fit ``r(t)=a+bt, theta(t)=omega t + phi``; return the reconstruction."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    cx, cy = _spiral_center(x, y)
    r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    A = np.vstack([t, np.ones_like(t)]).T
    ab, *_ = np.linalg.lstsq(A, r, rcond=None)
    r_fit = A @ ab
    z = (x - cx + 1j * (y - cy)) / (r_fit + 1e-9)
    phi = float(np.median(np.angle(z * np.exp(-1j * omega * t))))
    xr = cx + r_fit * np.cos(omega * t + phi)
    yr = cy + r_fit * np.sin(omega * t + phi)
    return xr, yr


def eom_dynamical_score(x, y, dt, family, fx, fy) -> float:
    """Dynamical score = ``1 - min(NMSE, 1)`` of the design-model fit.

    Higher is better; 1.0 means the trajectory follows the design equation of
    motion. A flat (constant) coordinate is treated as a perfect fit so a
    two-axis motion is not penalised for a stationary axis.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    t = np.arange(x.size) * dt
    if family == "spiral":
        omega = 2.0 * np.pi * (fx if fx is not None else fy)
        xr, yr = fit_spiral_recon(x, y, t, omega)
        nmse = 0.5 * (_nmse(x, xr) + _nmse(y, yr))
        return float(np.clip(1.0 - nmse, 0.0, 1.0))

    def coord(q, freq):
        if np.std(q) < 0.5:
            return 0.0
        if freq is not None:
            if family == "damped":
                nmse, _ = fit_damped(q, t, 2.0 * np.pi * freq)
            else:
                nmse = _nmse(q, fit_sinusoid(q, t, 2.0 * np.pi * freq))
            return nmse
        if family in ("linear", "unknown"):
            return _nmse(q, fit_poly2(q, t))
        # oscillatory family but no design frequency for this axis: no law to
        # match, so a stationary / law-free axis must not drag the score down
        return 0.0

    nmse = 0.5 * (coord(x, fx) + coord(y, fy))
    return float(np.clip(1.0 - nmse, 0.0, 1.0))


def fit_reconstruct(x, y, dt, family, fx, fy):
    """Noise-free model reconstructions of both coordinates.

    Used by the conservation probes so that pixel/numerical noise does not
    fake a violation of a physical invariant. For an exact design signal the
    reconstruction is identical to the input; for a noisy track it is the
    smooth law the track was expected to follow.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    t = np.arange(x.size) * dt
    if family == "spiral":
        omega = 2.0 * np.pi * (fx if fx is not None else fy)
        return fit_spiral_recon(x, y, t, omega)

    def _omega_of(f):
        return 2.0 * np.pi * f if f is not None else None

    return (_coord_recon(x, t, fx, family, _omega_of(fx)),
            _coord_recon(y, t, fy, family, _omega_of(fy)))


def conservation_score(x, y, dt, family, fx, fy,
                       center=None) -> tuple[float, str, float]:
    """Score conservation of the motion's invariant; returns
    ``(score, invariant_name, raw_invariant)``.

    The invariant is evaluated on the *model-fitted* trajectory so that pixel
    noise does not fake a violation. ``score`` is in [0, 1]; 1.0 means the
    invariant is conserved.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if family == "unknown":
        return float("nan"), "unknown", float("nan")
    xf, yf = fit_reconstruct(x, y, dt, family, fx, fy)

    if family == "linear":
        # uniform-speed -> kinetic energy is constant
        vx, vy = _central_diff(xf, dt), _central_diff(yf, dt)
        ke = 0.5 * (vx ** 2 + vy ** 2)
        cv = _cv(ke)
        return float(np.clip(1.0 - cv / _TOL_CV, 0.0, 1.0)), "kinetic_energy", cv

    if family == "circular":
        # uniform circular motion -> radius (distance from centre) is constant
        cx, cy = _spiral_center(xf, yf)
        r = np.sqrt((xf - cx) ** 2 + (yf - cy) ** 2)
        cv = _cv(r)
        return float(np.clip(1.0 - cv / _TOL_CV, 0.0, 1.0)), "radius", cv

    if family == "harmonic":
        fxu = fx if fx is not None else 0.0
        q0 = center[0] if center else float(np.mean(xf))
        w = 2.0 * np.pi * fxu
        v = _central_diff(xf, dt)
        e = 0.5 * v ** 2 + 0.5 * w ** 2 * (xf - q0) ** 2
        cv = _cv(e)
        return float(np.clip(1.0 - cv / _TOL_CV, 0.0, 1.0)), "sho_energy_x", cv

    if family == "lissajous":
        cx0 = center[0] if center else float(np.mean(xf))
        cy0 = center[1] if center else float(np.mean(yf))
        cvs = []
        for coord, freq, q0 in ((xf, fx, cx0), (yf, fy, cy0)):
            if freq is None:
                continue
            w = 2.0 * np.pi * freq
            v = _central_diff(coord, dt)
            e = 0.5 * v ** 2 + 0.5 * w ** 2 * (coord - q0) ** 2
            cvs.append(_cv(e))
        cv = float(np.mean(cvs)) if cvs else 0.0
        return float(np.clip(1.0 - cv / _TOL_CV, 0.0, 1.0)), "sho_energy_xy", cv

    if family == "damped":
        fxu = fx if fx is not None else 0.0
        w = 2.0 * np.pi * fxu
        v = _central_diff(xf, dt)
        q0 = center[0] if center else float(np.mean(xf))
        e = 0.5 * v ** 2 + 0.5 * w ** 2 * (xf - q0) ** 2
        e = np.clip(e, 1e-6, None)
        le = np.log(e)
        tt = np.arange(xf.size) * dt
        A = np.vstack([tt, np.ones_like(tt)]).T
        coef, *_ = np.linalg.lstsq(A, le, rcond=None)
        pred = A @ coef
        ss_res = float(np.sum((le - pred) ** 2))
        ss_tot = float(np.sum((le - np.mean(le)) ** 2))
        r2 = 1.0 - ss_res / (ss_tot + 1e-12)
        return float(np.clip(r2, 0.0, 1.0)), "decay_linearity", r2

    if family == "spiral":
        # a spiral obeys r(t) = a + b t, so the invariant is the linearity of
        # radius vs time. Evaluate on the raw radius (noise-robust): a clean
        # spiral has R^2 ~ 1; a corrupt / gappy track deviates from the law.
        if center:
            cx, cy = float(center[0]), float(center[1])
        else:
            cx, cy = _spiral_center(x, y)
        r = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        tt = np.arange(x.size) * dt
        A = np.vstack([tt, np.ones_like(tt)]).T
        coef, *_ = np.linalg.lstsq(A, r, rcond=None)
        pred = A @ coef
        ss_res = float(np.sum((r - pred) ** 2))
        ss_tot = float(np.sum((r - np.mean(r)) ** 2))
        r2 = 1.0 - ss_res / (ss_tot + 1e-12)
        return float(np.clip(r2, 0.0, 1.0)), "radial_linearity", r2

    return float("nan"), "unknown", float("nan")


# --- public entry points ---------------------------------------------------- #
@dataclass
class PhysicsReport:
    """All three probes for one trajectory (and, optionally, its delta vs a
    reference such as ground truth)."""

    family: str
    invariant: str
    conservation_score: float
    invariant_value: float
    dynamical_score: float
    teleport: dict = field(default_factory=dict)
    delta_conservation: float | None = None
    delta_dynamical: float | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "family": self.family,
            "invariant": self.invariant,
            "conservation_score": round(float(self.conservation_score), 4),
            "invariant_value": round(float(self.invariant_value), 4),
            "dynamical_score": round(float(self.dynamical_score), 4),
            "teleport": {k: (round(v, 4) if isinstance(v, float) else v)
                         for k, v in self.teleport.items()},
        }
        if self.delta_conservation is not None:
            out["delta_conservation"] = round(float(self.delta_conservation), 4)
        if self.delta_dynamical is not None:
            out["delta_dynamical"] = round(float(self.delta_dynamical), 4)
        return out


def score_trajectory(
    x: Sequence[float],
    y: Sequence[float],
    dt: float,
    family: str,
    fx: float | None = None,
    fy: float | None = None,
    center: tuple[float, float] | None = None,
) -> dict:
    """Run every probe on a single trajectory and return a plain dict.

    ``family`` selects the conservation invariant (``linear`` / ``circular`` /
    ``harmonic`` / ``lissajous`` / ``damped`` / ``spiral`` / ``unknown``).
    The optional ``center`` and ``fx`` / ``fy`` are the design parameters of
    the expected motion; they let the probes be judged against a known law
    rather than only against noise.
    """
    if dt <= 0:
        raise FFTError(f"dt must be > 0, got {dt}")
    cons, inv, raw = conservation_score(x, y, dt, family, fx, fy, center)
    dyn = eom_dynamical_score(x, y, dt, family, fx, fy)
    tele = teleport_metric(x, y, dt)
    return {
        "family": family,
        "invariant": inv,
        "conservation_score": cons,
        "invariant_value": raw,
        "dynamical_score": dyn,
        "teleport": tele,
    }


def compare_trajectories(
    x: Sequence[float], y: Sequence[float],
    ref_x: Sequence[float], ref_y: Sequence[float],
    dt: float, family: str,
    fx: float | None = None, fy: float | None = None,
    center: tuple[float, float] | None = None,
) -> dict:
    """Score a trajectory and a reference with the same probes; add deltas.

    ``delta_conservation`` / ``delta_dynamical`` are the candidate minus the
    reference (``cand - ref``): a candidate faithful to the reference is ~0,
    while a corrupt / swapped / gappy candidate is *negative* (worse than the
    reference). The result is the candidate's :func:`score_trajectory` dict
    plus the two deltas.
    """
    cand = score_trajectory(x, y, dt, family, fx, fy, center)
    ref = score_trajectory(ref_x, ref_y, dt, family, fx, fy, center)
    cand["delta_conservation"] = cand["conservation_score"] - ref["conservation_score"]
    cand["delta_dynamical"] = cand["dynamical_score"] - ref["dynamical_score"]
    return cand


def object_physics(
    result, dt: float, family: str = "unknown",
    fx: float | None = None, fy: float | None = None,
    center: tuple[float, float] | None = None,
) -> PhysicsReport:
    """Score one :class:`~.tracker.ObjectResult` (or any object with a
    ``points`` list of ``x_px`` / ``y_px`` / ``time_s`` fields).

    The time step is taken from the supplied ``dt`` (usually ``1 / fps``).
    A reference trajectory is not needed: the probes judge the candidate
    against the *laws* selected by ``family``.
    """
    pts = getattr(result, "points", result)
    if len(pts) < 4:
        raise FFTError(
            f"object {getattr(result, 'name', '<unnamed>')!r} has "
            f"{len(pts)} points; at least 4 are required"
        )
    xs = np.array([p.x_px for p in pts], dtype=float)
    ys = np.array([p.y_px for p in pts], dtype=float)
    s = score_trajectory(xs, ys, dt, family, fx, fy, center)
    return PhysicsReport(
        family=s["family"],
        invariant=s["invariant"],
        conservation_score=s["conservation_score"],
        invariant_value=s["invariant_value"],
        dynamical_score=s["dynamical_score"],
        teleport=s["teleport"],
    )

