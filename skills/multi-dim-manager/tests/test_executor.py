"""Tests for plugin execution and contract handling."""

import pytest
import sys

from scripts.common import sha256
from scripts.executor import ExecutionResult, run_plugin
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
    # With shell=True, a missing executable does not raise; it is recorded as a
    # failed round instead. The PluginError path is covered by the timeout test.
    res = run_plugin(
        6, {"a": 1}, "this_command_does_not_exist_xyz {OUT}",
        tmp_path / "work", tmp_path / "out",
    )
    assert res.exit_code != 0
    assert res.status in ("failed", "error")


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
