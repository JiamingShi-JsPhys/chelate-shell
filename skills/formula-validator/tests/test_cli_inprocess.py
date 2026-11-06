"""In-process tests for the CLI and the core engine it drives.

The rest of the suite exercises the skill through ``scripts/cli.py`` as a
*subprocess* (see ``conftest.run_cli``). That is the correct end-to-end path,
but coverage.py only measures the parent process, so the CLI layer and the
engine it calls (``pipeline``, ``breakpoint``, ``matrixprops``, ``report``)
show up as uncovered. These tests call ``cli.main`` *in the same process*, so
those lines are actually measured - which is also how task-organizer tests
its entry point.
"""

from __future__ import annotations

import json

import pytest

from scripts import cli


def _run(argv, capsys):
    """Call cli.main in-process, return (summary dict, exit code)."""
    try:
        rc = cli.main(argv)
    except SystemExit as exc:
        rc = exc.code
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines, f"cli produced no output for {argv!r}; stdout was:\n{out}"
    return json.loads(lines[-1]), rc


# --- validate ---------------------------------------------------------------

def test_validate_identity_passes(capsys):
    summary, rc = _run(
        ["validate", "--expr", "1/(x*(1+x)) = 1/x - 1/(1+x)",
         "--samples", "300", "--report", "-"], capsys)
    assert summary["verdict"] == "pass"
    assert rc == 0


def test_validate_definition_is_unknown(capsys):
    summary, rc = _run(
        ["validate", "--expr", "E = m*c**2",
         "--units", "E=J", "--units", "m=kg", "--units", "c=m/s",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] == "unknown"
    assert rc == 2


def test_validate_dimension_mismatch_fails(capsys):
    summary, rc = _run(
        ["validate", "--expr", "E = m",
         "--units", "E=J", "--units", "m=kg",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] == "fail"
    assert "dimension" in summary["failed_checks"]
    assert rc == 1


def test_validate_numeric_mismatch_fails(capsys):
    # Neither side is a bare symbol, so the numeric check actually runs.
    summary, rc = _run(
        ["validate", "--expr", "x + 1 = x + 2",
         "--samples", "300", "--report", "-"], capsys)
    assert summary["verdict"] == "fail"
    assert "numeric" in summary["failed_checks"]
    assert rc == 1


def test_validate_with_limit_point_and_no_symbolic(capsys):
    # --critical exercises the extra limit-point path; --no-symbolic skips D5.
    summary, rc = _run(
        ["validate", "--expr", "1/(1-x**2) = 1/((1-x)*(1+x))",
         "--critical", "x=1", "--no-symbolic",
         "--samples", "300", "--report", "-"], capsys)
    assert summary["verdict"] == "pass"
    assert rc == 0


def test_validate_infer_runs(capsys):
    # --infer guesses units for undeclared symbols; we only assert the run
    # terminates with a defined verdict and does not crash.
    summary, rc = _run(
        ["validate", "--expr", "F = m*a", "--infer",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] in ("pass", "fail", "unknown")
    assert rc in (0, 1, 2)


# --- check ------------------------------------------------------------------

def test_check_expect_zero_passes(capsys):
    summary, rc = _run(
        ["check", "--expr", "sin(x)**2+cos(x)**2-1", "--expect-zero",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] == "pass"
    assert rc == 0


def test_check_expect_zero_fails_for_nonzero(capsys):
    summary, rc = _run(
        ["check", "--expr", "x", "--expect-zero",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] == "fail"
    assert rc == 1


def test_check_symbols_flag_runs(capsys):
    # --symbols I forces I to a plain symbol; the run must not crash.
    summary, rc = _run(
        ["check", "--expr", "I**2", "--symbols", "I",
         "--report", "-"], capsys)
    assert rc in (0, 2)


# --- derive -----------------------------------------------------------------

def test_derive_passes_for_equal_steps(capsys):
    summary, rc = _run(
        ["derive", "--steps", "x**2 - 1", "--steps", "(x-1)*(x+1)",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] == "pass"
    assert rc == 0


def test_derive_locates_break(capsys):
    summary, rc = _run(
        ["derive", "--steps", "x**2", "--steps", "x**3",
         "--samples", "200", "--report", "-"], capsys)
    assert summary["verdict"] == "fail"
    assert summary.get("breakpoint") is not None
    assert rc == 1


def test_derive_needs_two_steps(capsys):
    # One step is not a chain; CLI refuses before calling the engine.
    summary, rc = _run(
        ["derive", "--steps", "x**2", "--report", "-"], capsys)
    assert summary["verdict"] == "error"
    assert rc == 4


# --- matrix -----------------------------------------------------------------

def test_matrix_hermitian_unitary_passes(capsys):
    summary, rc = _run(
        ["matrix", "--matrix", "Matrix([[0,1],[1,0]])",
         "--report", "-"], capsys)
    assert summary["verdict"] == "pass"
    assert rc == 0


def test_matrix_nonunitary_fails(capsys):
    summary, rc = _run(
        ["matrix", "--matrix", "Matrix([[1,0],[0,2]])",
         "--report", "-"], capsys)
    assert summary["verdict"] == "fail"
    assert "unitary" in summary["failed"]
    assert rc == 1


def test_matrix_from_file(tmp_path, capsys):
    p = tmp_path / "m.txt"
    p.write_text("Matrix([[1,0],[0,1]])", encoding="utf-8")
    summary, rc = _run(["matrix", "--matrix-file", str(p), "--report", "-"], capsys)
    assert summary["verdict"] == "pass"
    assert rc == 0


# --- error surface ----------------------------------------------------------

def test_validate_parse_error_exits_3(capsys):
    # Bare-subscript summation is rejected, not guessed.
    summary, rc = _run(
        ["validate", "--expr", "sum_i F_ij", "--report", "-"], capsys)
    assert summary["verdict"] == "parse_error"
    assert rc == 3


def test_missing_subcommand_exits(capsys):
    with pytest.raises(SystemExit):
        cli.main([])


def test_version_exits(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])


# --- report rendering is covered in-process ----------------------------------

def test_report_rendering_on_pass(capsys):
    # --stdout-report prints the Markdown report (not JSON), so we assert on
    # the rendered text directly.
    rc = cli.main(
        ["validate", "--expr", "1/(x*(1+x)) = 1/x - 1/(1+x)",
         "--samples", "200", "--stdout-report"])
    out = capsys.readouterr().out
    assert "#" in out  # markdown heading rendered
    assert rc == 0


def test_report_rendering_on_fail(capsys):
    rc = cli.main(
        ["validate", "--expr", "E = m",
         "--units", "E=J", "--units", "m=kg",
         "--samples", "200", "--stdout-report"])
    out = capsys.readouterr().out
    assert "#" in out
    assert rc == 1


def test_report_written_to_explicit_path(tmp_path, capsys):
    # Exercises the file-writing branch of _write_report (not just stdout).
    target = tmp_path / "report.md"
    summary, rc = _run(
        ["validate", "--expr", "1/(x*(1+x)) = 1/x - 1/(1+x)",
         "--samples", "200", "--report", str(target)], capsys)
    assert summary["verdict"] == "pass"
    assert target.is_file()
    assert "#" in target.read_text(encoding="utf-8")
