"""formula-validator acceptance: D1-D5 legacy layers + pint unit layer."""
from __future__ import annotations

import json
import subprocess
import sys

from conftest import REPO_ROOT, SKILLS_DIR, run_in_skill

# --- legacy SymPy D1-D5 pipeline (the code path scripts/cli.py uses) --------

VALIDATE_OK = """
import json, sys
sys.path.insert(0, "skills/formula-validator")
from scripts.core.pipeline import validate_equation
r = validate_equation("2*(a+b) = 2*a + 2*b", {})
print(json.dumps({"verdict": r.get("verdict"),
                  "errors": r.get("errors", []),
                  "reason": r.get("reason")}))
"""

VALIDATE_DIM_FAIL = """
import json, sys
sys.path.insert(0, "skills/formula-validator")
from scripts.core.pipeline import validate_equation
r = validate_equation("F = m*a", {"F": "N", "m": "kg", "a": "s"})
print(json.dumps({"verdict": r.get("verdict"),
                  "errors": r.get("errors", [])}))
"""

VALIDATE_PARSE_FAIL = """
import json, sys
sys.path.insert(0, "skills/formula-validator")
from scripts.core.pipeline import validate_equation
try:
    r = validate_equation("F = = m*a", {})
    print(json.dumps({"raised": False, "verdict": r.get("verdict"),
                      "errors": r.get("errors", [])}))
except Exception as exc:
    print(json.dumps({"raised": True, "etype": type(exc).__name__}))
"""

# --- pint physical-unit layer (v1.1.0 merge) --------------------------------

PINT_OK = """
import json, sys
sys.path.insert(0, "skills/formula-validator")
from scripts.core.pint_units import check_equation_units
r = check_equation_units("g*h = v**2/2",
                         {"g": "m/s**2", "h": "m", "v": "m/s"})
print(json.dumps({"status": r["status"], "reason": r.get("reason", "")}))
"""

PINT_BAD = """
import json, sys
sys.path.insert(0, "skills/formula-validator")
from scripts.core.pint_units import check_equation_units
r = check_equation_units("F = m", {"F": "N", "m": "kg"})
print(json.dumps({"status": r["status"], "reason": r.get("reason", "")}))
"""


def test_d1_d5_pipeline_proves_distributive_identity():
    out = run_in_skill("formula-validator", VALIDATE_OK)
    assert out["verdict"] == "pass", out
    assert out["errors"] == [], out


def test_dimension_layer_rejects_mismatch():
    out = run_in_skill("formula-validator", VALIDATE_DIM_FAIL)
    assert out["verdict"] == "fail", out
    assert any(e.get("check") == "dimension" for e in out["errors"]), out


def test_parse_layer_rejects_malformed_equation():
    """A malformed equation must never silently pass: legacy raises, and the
    adapter turns that into a gate verdict (never a crash)."""
    out = run_in_skill("formula-validator", VALIDATE_PARSE_FAIL)
    if out["raised"]:
        assert out["etype"]  # some parse error surfaced
    else:
        assert out["verdict"] in ("fail", "unknown"), out
        assert out["errors"] or out["verdict"] == "unknown", out


def test_pint_layer_consistent():
    out = run_in_skill("formula-validator", PINT_OK)
    assert out["status"] == "pass", out


def test_pint_layer_rejects_mismatch():
    out = run_in_skill("formula-validator", PINT_BAD)
    assert out["status"] == "fail", out
    assert out["reason"]


def test_adapter_emits_gate_for_dimension_fail(workspace):
    """End-to-end: the run.py adapter writes a standard gate_result."""
    cmd = [sys.executable, str(SKILLS_DIR / "formula-validator" / "run.py"),
           "--root", str(workspace), "--action", "gate",
           "--", "--expr", "F = m*a", "--units", "F=N", "--units", "m=kg",
           "--units", "a=s"]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                          text=True, timeout=300)
    gates = sorted((workspace / "process" / "gates").glob(
        "formula-validator_*.json"))
    assert gates, f"no gate written; stdout={proc.stdout[-500:]}"
    gate = json.loads(gates[-1].read_text(encoding="utf-8"))
    assert gate["skill"] == "formula-validator"
    assert gate["status"] in ("FAIL", "UNVERIFIED")
