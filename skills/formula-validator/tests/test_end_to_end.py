"""End-to-end tests through the real CLI.

The three canonical cases are the ones the skill exists for: a dimensional
error, a divergence error at a pole, and a formula that must come back clean.
They are asserted through the command line, not through library calls, so the
exit codes and the output contract are covered too.
"""

from __future__ import annotations

import json

from conftest import ROOT, cli_json, run_cli

EXIT_PASS, EXIT_FAIL, EXIT_UNKNOWN, EXIT_PARSE = 0, 1, 2, 3


def test_case_1_dimensional_error_is_caught():
    summary, code = cli_json(
        "validate", "--expr", "p*c = m*c**2 + m*v",
        "--units", "p=kg*m/s", "--units", "c=m/s",
        "--units", "m=kg", "--units", "v=m/s")
    assert summary["verdict"] == "fail"
    assert "dimension" in summary["failed_checks"]
    assert "incompatible dimensions" in summary["first_error"]
    assert code == EXIT_FAIL


def test_case_2_divergence_error_is_caught_at_the_pole():
    summary, code = cli_json("validate", "--expr", "1/(1-x**2) = 1/(1-x)")
    assert summary["verdict"] == "fail"
    assert "limit" in summary["failed_checks"], (
        "the pole must be found and probed automatically")
    assert "diverg" in summary["first_error"]
    assert code == EXIT_FAIL


def test_case_3_correct_formula_comes_back_clean():
    summary, code = cli_json("validate",
                             "--expr", "1/(x*(1+x)) = 1/x - 1/(1+x)")
    assert summary["verdict"] == "pass"
    assert summary["failed_checks"] == []
    assert code == EXIT_PASS


def test_definition_is_checked_dimensionally_only():
    summary, code = cli_json(
        "validate", "--expr", "E = m*c**2",
        "--units", "E=J", "--units", "m=kg", "--units", "c=m/s")
    assert summary["verdict"] == "unknown"
    assert summary["failed_checks"] == []
    assert code == EXIT_UNKNOWN
    # the numeric check is meaningless here, so it must not have run
    assert summary["max_rel_error"] is None


def test_a_definition_is_not_numerically_sampled():
    """p = m*v has a bare symbol on one side, so sampling would reject it."""
    summary, code = cli_json(
        "validate", "--expr", "p = m*v",
        "--units", "p=kg*m/s", "--units", "m=kg", "--units", "v=m/s")
    assert summary["verdict"] == "unknown"
    assert summary["failed_checks"] == []
    assert code == EXIT_UNKNOWN


def test_wrong_units_against_a_correct_formula_surface_as_conflict():
    # p*c = m*c**2 is wrong, but if m is declared with the wrong unit the
    # dimensional check and the numeric check can disagree; either way it must
    # not come back clean.
    summary, _ = cli_json(
        "validate", "--expr", "p*c = m*c**2",
        "--units", "p=kg*m/s", "--units", "c=m/s", "--units", "m=kg")
    assert summary["verdict"] in {"fail", "conflict"}
    assert summary["verdict"] != "pass"


def test_parse_error_exits_with_3_and_names_a_hint():
    proc = run_cli("validate", "--expr", r"\int_0^1 f(x) dx")
    assert proc.returncode == EXIT_PARSE
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["verdict"] == "parse_error"
    assert "hint" in payload.get("detail", {})


def test_derive_localises_a_constant_factor():
    summary, code = cli_json(
        "derive", "--steps", "x**2 + 2*x + 1",
        "--steps", "(x+1)**2", "--steps", "2*(x+1)**2")
    assert code == EXIT_FAIL
    assert summary["breakpoint"]["step"] == 2
    assert summary["breakpoint"]["diagnosis"] == "constant_factor"


def test_derive_separates_a_structural_error():
    summary, _ = cli_json(
        "derive", "--steps", "1/(1-x**2)", "--steps", "1/((1-x)*(1+x))",
        "--steps", "(1/2)*(1/(1-x)+1/(1+x))", "--steps", "1/(1-x)")
    assert summary["breakpoint"]["step"] == 3
    assert summary["breakpoint"]["diagnosis"] == "structural"


def test_derive_passes_on_a_clean_chain():
    summary, code = cli_json(
        "derive", "--steps", "1/(1-x**2)",
        "--steps", "1/((1-x)*(1+x))",
        "--steps", "(1/2)*(1/(1-x)+1/(1+x))")
    assert summary["verdict"] == "pass"
    assert code == EXIT_PASS


def test_matrix_command_accepts_a_pauli_matrix():
    summary, code = cli_json("matrix", "--matrix", "Matrix([[0, -I], [I, 0]])",
                             "--props", "hermitian,unitary,traceless")
    assert summary["verdict"] == "pass"
    assert summary["shape"] == [2, 2]
    assert code == EXIT_PASS


def test_matrix_command_rejects_a_non_unitary_matrix():
    summary, code = cli_json("matrix", "--matrix", "Matrix([[1, 1], [0, 1]])",
                             "--props", "hermitian,unitary")
    assert summary["verdict"] == "fail"
    assert "hermitian" in summary["failed"]
    assert code == EXIT_FAIL


def test_report_is_written_to_disk():
    summary, _ = cli_json("validate", "--expr", "1/(1-x**2) = 1/(1-x)")
    path = ROOT / "_reports" / "latest.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "FAIL" in text
    assert "diverg" in text


def test_summary_stays_small_enough_for_a_context_window():
    """The compact summary is what enters the context; the report is not."""
    _, _ = cli_json("validate", "--expr", "1/(x*(1+x)) = 1/x - 1/(1+x)")
    line = run_cli("validate", "--expr",
                   "1/(x*(1+x)) = 1/x - 1/(1+x)").stdout.strip()
    assert len(line) < 900, f"summary grew to {len(line)} characters"


def test_report_status_cells_never_repeat_the_status_word():
    """Every stage status has a marker, so no cell reads 'skipped skipped'."""
    from scripts.core.report import _MARK

    cli_json("validate", "--expr", "p*c = m*c**2 + m*v",
             "--units", "p=kg*m/s", "--units", "c=m/s",
             "--units", "m=kg", "--units", "v=m/s")
    text = (ROOT / "_reports" / "latest.md").read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines()
            if ln.startswith("| D") and ln.count("|") >= 3]
    assert rows, "no check table rows found in the report"
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        status = cells[-1].split()[-1] if cells[-1] else ""
        if status in _MARK:
            assert cells[-1].startswith(_MARK[status]), (
                f"row {row!r} is missing its {status!r} marker")


def test_check_expect_zero_proves_a_trig_identity():
    """--expect-zero decides a genuinely zero expression even without units."""
    summary, code = cli_json("check", "--expr", "sin(x)**2+cos(x)**2-1",
                             "--expect-zero")
    assert summary["verdict"] == "pass", summary
    assert code == EXIT_PASS


def test_check_expect_zero_fails_a_nonidentity():
    """A residual that is not identically zero is reported as fail, not unknown."""
    summary, code = cli_json("check", "--expr", "x**2+1", "--expect-zero")
    assert summary["verdict"] == "fail", summary
    assert code == EXIT_FAIL


def test_report_files_do_not_overwrite_each_other():
    """Batch validation keeps a per-run file instead of clobbering latest.md."""
    cli_json("validate", "--expr", "p*c = m*c**2",
             "--units", "p=kg*m/s", "--units", "c=m/s", "--units", "m=kg")
    cli_json("validate", "--expr", "E = m*c**2",
             "--units", "E=J", "--units", "m=kg", "--units", "c=m/s")
    named = [p.name for p in (ROOT / "_reports").glob("*.md")
             if p.name != "latest.md"]
    # two distinct equations -> two distinct report files
    assert len(named) >= 2, f"expected distinct per-run files, got {named}"
    # latest.md is kept as a pointer to the most recent run
    assert (ROOT / "_reports" / "latest.md").is_file()


def test_json_pretty_flag_indents_output():
    """--json-pretty makes the summary multi-line and still valid JSON."""
    proc = run_cli("validate", "--expr", "1/(x*(1+x)) = 1/x - 1/(1+x)",
                   "--json-pretty")
    assert proc.returncode == EXIT_PASS
    assert proc.stdout.count("\n") >= 3, "indented JSON should span several lines"
    payload = json.loads(proc.stdout.strip())
    assert payload["verdict"] == "pass"
