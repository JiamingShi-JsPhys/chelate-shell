"""Tests for plugin execution and contract handling."""

import sys

import pytest

from scripts.common import sha256
from scripts.executor import (ExecutionResult, run_plugin,
                              split_plugin_command)
from scripts.errors import PluginError


def test_run_plugin_success(plugin_factory, tmp_path):
    cmd = plugin_factory("ok")
    res = run_plugin(1, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out", timeout=10)
    assert isinstance(res, ExecutionResult)
    assert res.exit_code == 0
    assert res.status == "success"
    assert res.result_data == {"ok": True, "n": 1}
    assert res.input_hash and res.output_hash
    assert res.output_hash != res.input_hash


def test_run_plugin_failure_exit_1(plugin_factory, tmp_path):
    cmd = plugin_factory("fail")
    res = run_plugin(2, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out")
    assert res.exit_code == 1
    assert res.status == "failed"


def test_run_plugin_error_exit_2(plugin_factory, tmp_path):
    cmd = plugin_factory("error")
    res = run_plugin(3, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out")
    assert res.exit_code == 2
    assert res.status == "error"


def test_run_plugin_missing_output_file(plugin_factory, tmp_path):
    cmd = plugin_factory("silent")  # exits 0 but writes nothing
    res = run_plugin(4, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out")
    assert res.exit_code == 0
    assert res.result_data is None
    assert res.output_hash == sha256(b"NO_OUTPUT")


def test_run_plugin_requires_out_placeholder(plugin_factory, tmp_path):
    cmd = plugin_factory("ok").replace("{OUT}", "fixed.json")
    with pytest.raises(PluginError):
        run_plugin(5, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out")


def test_run_plugin_unknown_command_is_recorded(tmp_path):
    # Without a shell there is nothing to translate "command not found" into
    # exit code 127, so the executor records that outcome itself. The
    # PluginError path is covered by the timeout and shell-syntax tests.
    res = run_plugin(
        6, {"a": 1}, "this_command_does_not_exist_xyz {OUT}",
        tmp_path / "work", tmp_path / "out",
    )
    assert res.exit_code != 0
    assert res.status in ("failed", "error")
    assert "not found" in res.stderr


def test_run_plugin_timeout(plugin_factory, tmp_path):
    cmd = plugin_factory("sleep")
    with pytest.raises(PluginError):
        run_plugin(7, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out", timeout=1)


def test_run_plugin_invalid_json_output_is_none(tmp_path):
    # Plugin exits 0 but writes garbage to the result file.
    script = tmp_path / "bin" / "p.py"
    (tmp_path / "bin").mkdir()
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        "Path(sys.argv[2]).write_text('not json{')"  # missing '}'
        "\nraise SystemExit(0)\n",
        encoding="utf-8",
    )
    cmd = f"{sys.executable} {script} {{PARAMS}} {{OUT}}"
    res = run_plugin(8, {"a": 1}, cmd, tmp_path / "work", tmp_path / "out")
    assert res.exit_code == 0
    assert res.result_data is None  # unparseable JSON is treated as no result


# ------------------------------------------------------- no shell (CVE class)

def test_run_plugin_rejects_shell_operators(tmp_path):
    """A template using shell syntax must be refused, not quietly reinterpreted
    as literal arguments."""
    for template in ("echo hi && echo {OUT}",
                     "echo hi; touch pwned {OUT}",
                     "cat {PARAMS} | tee {OUT}",
                     "echo hi > {OUT}"):
        with pytest.raises(PluginError, match="shell operator"):
            run_plugin(9, {"a": 1}, template, tmp_path / "work",
                       tmp_path / "out")


def test_run_plugin_accepts_argument_list(plugin_factory, tmp_path):
    """plugin.command may be given as a ready-made list (the safest form on
    Windows, where no quoting rules apply at all)."""
    argv = split_plugin_command(plugin_factory("ok"))
    res = run_plugin(10, {"a": 1}, argv, tmp_path / "work", tmp_path / "out",
                     timeout=10)
    assert res.exit_code == 0
    assert res.result_data == {"ok": True, "n": 1}


def test_run_plugin_quoted_path_with_spaces_stays_one_argument(tmp_path):
    """A workspace path containing a space must reach the plugin intact.

    Substitution happens per token *after* splitting, so the quoted template
    token survives as a single argv entry on every platform.
    """
    spaced = tmp_path / "a dir with spaces"
    (spaced / "bin").mkdir(parents=True)
    script = spaced / "bin" / "p.py"
    script.write_text(
        "import sys, json\n"
        "from pathlib import Path\n"
        "Path(sys.argv[2]).write_text(json.dumps({'n': len(sys.argv)}))\n",
        encoding="utf-8",
    )
    cmd = f'"{sys.executable}" "{script}" {{PARAMS}} {{OUT}}'
    res = run_plugin(11, {"a": 1}, cmd, spaced / "work", spaced / "out",
                     timeout=10)
    assert res.exit_code == 0, res.stderr
    assert res.result_data == {"n": 3}
