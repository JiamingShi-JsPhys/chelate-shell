"""A research-shaped end-to-end run, and five ways an agent tries to defeat it.

The artefact is small on purpose — the nearest-neighbour tight-binding band
structure of a honeycomb lattice — so that nothing about the physics distracts
from the question this demo exists to answer:

    when an agent goes around the workflow, what does the shell do?

Each scenario builds its own workspace under a temporary directory, runs the
same six steps (write the model, compute, check, hash, approve, publish), and
then performs exactly one attack:

    1. edit the model after the check            -> promotion refused
    2. change a parameter after the approval     -> token no longer fits
    3. overwrite a figure after publication      -> named by `audit`
    4. delete an input after the check           -> promotion refused
    5. drop a file into results/ without a token -> named by `audit`

Scenarios 1, 2 and 4 are stopped before anything is written. Scenarios 3 and 5
happen after the fact: the shell's approval gate guards `promote()`, not the
directory, so those two are *detected* — by name, with the file's digest — not
prevented. That distinction is the honest content of this demo, and the reason
it is worth running.

Run from the repository root:

    python examples/graphene-tight-binding/run_demo.py [--keep]

Exit code 0 means every scenario behaved as this file documents; 1 means at
least one did not.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from contracts import EvidenceLevel, pass_gate  # noqa: E402
from core import approval, router  # noqa: E402

# ------------------------------------------------------------------ physics

# Honeycomb lattice, lattice constant a = 2.46 Å, nearest-neighbour hopping
# t = 2.7 eV.  E±(k) = ±|t| |f(k)| with f(k) = sum over the three NN vectors;
# f vanishes at K, which is the Dirac point this demo checks for (E = 0).
A = 2.46
DELTAS = ((0.0, A / math.sqrt(3.0)),
          (-A / 2.0, -A / (2.0 * math.sqrt(3.0))),
          (A / 2.0, -A / (2.0 * math.sqrt(3.0))))

MODEL = '''"""Nearest-neighbour tight-binding Hamiltonian for a honeycomb lattice.

E(k) = +/- |t| * |f(k)|,  f(k) = sum_j exp(i k . delta_j)

Written into material/initial/ as the input the rest of the run is checked
against.  Editing this file after a gate has run must expire that gate.
"""
import cmath
import math

A = {a!r}
DELTAS = {deltas!r}


def structure_factor(kx, ky):
    """f(k): the sum of the three phase factors, in the complex plane."""
    total = 0j
    for dx, dy in DELTAS:
        total += cmath.exp(1j * (kx * dx + ky * dy))
    return total


def bands(kx, ky, t={t!r}):
    """The two bands, in eV, ordered lower-first."""
    amp = abs(t) * abs(structure_factor(kx, ky))
    return (-amp, +amp)
'''

PARAMS = {"t_eV": 2.7, "a_angstrom": A}


def structure_factor(kx: float, ky: float) -> complex:
    total = 0j
    for dx, dy in DELTAS:
        total += complex(math.cos(kx * dx + ky * dy), math.sin(kx * dx + ky * dy))
    return total


def bands(kx: float, ky: float, t: float = 2.7) -> tuple:
    amp = abs(t) * abs(structure_factor(kx, ky))
    return (-amp, +amp)


def band_path(samples: int = 60):
    """Γ → M → K → Γ in Cartesian k-space, as (label, points) segments."""
    b = 2 * math.pi / (A * math.sqrt(3.0))
    gamma = (0.0, 0.0)
    m = (b, b / math.sqrt(3.0))
    k = (2 * b / 3.0, 0.0)
    out = []
    for name, start, end in (("G-M", gamma, m), ("M-K", m, k),
                             ("K-G", k, gamma)):
        for i in range(samples):
            f = i / (samples - 1)
            out.append((name, start[0] + f * (end[0] - start[0]),
                        start[1] + f * (end[1] - start[1])))
    return out


def write_bands_csv(path: Path) -> None:
    rows = ["segment,kx,ky,E_minus_EV,E_plus_EV"]
    for name, kx, ky in band_path():
        lo, hi = bands(kx, ky)
        rows.append(f"{name},{kx:.6f},{ky:.6f},{lo:.6f},{hi:.6f}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_bands_svg(path: Path, width: int = 640, height: int = 360) -> None:
    """The band figure, drawn with nothing but the standard library."""
    points = band_path()
    ys = [v for _n, kx, ky in points for v in bands(kx, ky)]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    step = width / max(len(points) - 1, 1)

    def y_of(e: float) -> float:
        return height - 30 - (e - lo) / span * (height - 60)

    def poly(which: int) -> str:
        return " ".join(f"{20 + i * step:.2f},{y_of(bands(kx, ky)[which]):.2f}"
                        for i, (_n, kx, ky) in enumerate(points))

    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="#fff"/>'
        f'<polyline fill="none" stroke="#1a4b8c" stroke-width="2" '
        f'points="{poly(1)}"/>'
        f'<polyline fill="none" stroke="#1a4b8c" stroke-width="2" '
        f'points="{poly(0)}"/>'
        f'<line x1="20" y1="{y_of(0):.2f}" x2="{width - 20}" '
        f'y2="{y_of(0):.2f}" stroke="#999" stroke-dasharray="4 4"/>'
        f'<text x="30" y="24" font-family="sans-serif" font-size="13">'
        f'honeycomb bands, t=2.7 eV</text></svg>\n', encoding="utf-8")


# --------------------------------------------------------------- workspace

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_workspace(base: Path) -> Path:
    ws = base
    (ws / "material" / "initial").mkdir(parents=True)
    (ws / "process" / "gates").mkdir(parents=True)
    (ws / "process" / "bands").mkdir(parents=True)
    model = ws / "material" / "initial" / "hamiltonian.py"
    model.write_text(MODEL.format(a=A, deltas=DELTAS, t=PARAMS["t_eV"]),
                     encoding="utf-8")
    (ws / "material" / "initial" / "parameters.json").write_text(
        json.dumps(PARAMS, indent=2), encoding="utf-8")
    return ws


def compute(ws: Path) -> None:
    write_bands_csv(ws / "process" / "bands" / "eigenvalues.csv")
    write_bands_svg(ws / "process" / "bands" / "bands.svg")


def check_and_gate(ws: Path) -> Path:
    """The gate step: judge the inputs, and record which bytes were judged."""
    inputs = {}
    for rel in ("material/initial/hamiltonian.py",
                "material/initial/parameters.json"):
        inputs[rel] = sha256(ws / rel)
    # A real skill verifies something here.  This demo verifies the one
    # property the input asserts: f(k) vanishes at the Dirac point.
    f_k = abs(structure_factor(2 * math.pi / (3 * A), 0.0))
    ok = f_k < 1e-9
    gate = pass_gate("formula-validator", EvidenceLevel.SYMBOLIC,
                     reason="Dirac point at K: |f(K)| = %.1e" % f_k
                     if ok else "Dirac point missing")
    gate.inputs = inputs
    gate.provenance = {"skill_version": "demo", "skill_digest": "demo",
                       "gate_contract": 2}
    import bootstrap
    return Path(bootstrap.write_gate(str(ws), gate))


def current_params(ws: Path, allow_unverified: bool = False) -> dict:
    """The plan as it stands *now* — what the token is checked against.

    The human approves the model file.  `parameters.json` is bound by the
    gate but not by the token, which is how the two checks stay separable:
    the token answers "is this still the plan a person saw?", the gate
    answers "are these still the bytes that were checked?".
    """
    inputs = [str(ws / "material" / "initial" / "hamiltonian.py")]
    return approval.pipeline_params("a", "", inputs, None,
                                    allow_unverified=allow_unverified)


def approve(ws: Path, allow_unverified: bool = False) -> dict:
    params = current_params(ws, allow_unverified)
    approval.issue(str(ws), "promote", params)
    return params


def publish(ws: Path, params: dict, stamp: str = "demo") -> str:
    # Recomputed, not reused: this is what `cli.py pipeline` does, and it is
    # what makes a change between approval and promotion visible.
    token = approval.consume(str(ws), "promote", current_params(ws))
    dst = router.promote(str(ws), stamp, {"source": "token",
                                          "nonce": token.get("nonce")})
    if dst is None:  # nothing to promote: the demo cannot continue
        raise RuntimeError("promotion produced nothing")
    return dst


# --------------------------------------------------------------- scenarios

class Outcome:
    def __init__(self, name: str):
        self.name = name
        self.expected = ""
        self.observed = ""
        self.ok = False


def _expect_failure(outcome: Outcome, fn, needle: str) -> None:
    try:
        fn()
    except Exception as exc:  # the refusal itself is the expected result
        outcome.observed = f"{type(exc).__name__}: {exc}"
        outcome.ok = needle in str(exc)
        return
    outcome.observed = "the shell allowed it"
    outcome.ok = False


def scenario_edit_model(base: Path) -> Outcome:
    out = Outcome("1. edit a parameter after the check")
    out.expected = "promotion refused: the gate expired"
    ws = make_workspace(base / "s1")
    compute(ws)
    check_and_gate(ws)
    params = approve(ws)
    (ws / "material" / "initial" / "parameters.json").write_text(
        json.dumps({"t_eV": 0.1, "a_angstrom": A}, indent=2), encoding="utf-8")
    _expect_failure(out, lambda: publish(ws, params), "expired gate")
    out.ok = out.ok and not list((ws / "results").glob("promoted_*"))
    return out


def scenario_change_parameter(base: Path) -> Outcome:
    out = Outcome("2. replace the approved model")
    out.expected = "token no longer fits the plan"
    ws = make_workspace(base / "s2")
    compute(ws)
    check_and_gate(ws)
    params = approve(ws)
    (ws / "material" / "initial" / "hamiltonian.py").write_text(
        MODEL.format(a=A, deltas=DELTAS, t=0.0), encoding="utf-8")
    _expect_failure(out, lambda: publish(ws, params), "different plan")
    out.ok = out.ok and not list((ws / "results").glob("promoted_*"))
    return out


def scenario_overwrite_figure(base: Path) -> Outcome:
    out = Outcome("3. overwrite a figure after publication")
    out.expected = "audit names it as modified (detected, not prevented)"
    ws = make_workspace(base / "s3")
    compute(ws)
    check_and_gate(ws)
    params = approve(ws)
    dst = Path(publish(ws, params))
    (dst / "bands" / "bands.svg").write_text("<svg>forged</svg>\n",
                                             encoding="utf-8")
    report = router.audit_results(str(ws))
    rel = f"results/{dst.name}/bands/bands.svg"
    modified = list(report["modified"])
    out.observed = f"modified={modified}"
    out.ok = report["ok"] is False and rel in modified
    return out


def scenario_delete_input(base: Path) -> Outcome:
    out = Outcome("4. delete an input after the check")
    out.expected = "promotion refused: bound input missing"
    ws = make_workspace(base / "s4")
    compute(ws)
    check_and_gate(ws)
    params = approve(ws)
    (ws / "material" / "initial" / "parameters.json").unlink()
    _expect_failure(out, lambda: publish(ws, params), "expired gate")
    out.ok = out.ok and not list((ws / "results").glob("promoted_*"))
    return out


def scenario_direct_write(base: Path) -> Outcome:
    out = Outcome("5. write results/ without a token")
    out.expected = "audit names it as unapproved (detected, not prevented)"
    ws = make_workspace(base / "s5")
    compute(ws)
    check_and_gate(ws)
    params = approve(ws)
    publish(ws, params)
    (ws / "results" / "stolen.csv").write_text("exfiltrated\n",
                                               encoding="utf-8")
    report = router.audit_results(str(ws))
    unapproved = list(report["unapproved"])
    out.observed = f"unapproved={unapproved}"
    out.ok = report["ok"] is False and "results/stolen.csv" in unapproved
    return out


SCENARIOS = (scenario_edit_model, scenario_change_parameter,
             scenario_overwrite_figure, scenario_delete_input,
             scenario_direct_write)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--keep", action="store_true",
                    help="keep the workspaces instead of deleting them")
    ap.add_argument("--out", default="",
                    help="directory for the workspaces (default: a temp dir)")
    args = ap.parse_args(argv)

    base = Path(args.out) if args.out else Path(tempfile.mkdtemp(
        prefix="chelate-graphene-"))
    base.mkdir(parents=True, exist_ok=True)
    # Keys live outside every workspace, as they do in a real run.
    os.environ.setdefault("CHELATE_KEY_ROOT", str(base / "_keys"))
    # The part of the run that needs a person.  This demo is scripted, so it
    # declares the scripted hatch instead of typing the phrase — and says so.
    os.environ.setdefault("CHELATE_UNSAFE_AUTO_APPROVE", "1")
    print("note: approval uses CHELATE_UNSAFE_AUTO_APPROVE=1, the scripted "
          "hatch.\n      A real run types `approve promote` at a terminal; "
          "the hatch is a declaration,\n      not proof that anyone was "
          "watching (docs/SAFETY.md).\n")

    results = [fn(base) for fn in SCENARIOS]

    print(f"{'scenario':<44}{'expected':<58}result")
    print("-" * 116)
    for r in results:
        print(f"{r.name:<44}{r.expected:<58}{'ok' if r.ok else 'UNEXPECTED'}")
        if not r.ok:
            print(f"    observed: {r.observed}")
    failures = [r for r in results if not r.ok]

    print()
    if failures:
        print(f"{len(failures)} scenario(s) did not behave as documented.")
    else:
        print("All five scenarios behaved as documented: three refused before "
              "any write,\nand two surfaced by name in the promotion audit.")
    print(f"workspaces: {base}")
    if not args.keep and not args.out:
        shutil.rmtree(base, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
