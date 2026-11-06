"""Tests for config loading."""

import pytest
from pathlib import Path

from scripts.config import Config, load_config
from scripts.errors import ConfigError


def test_load_config_from_dict():
    cfg = load_config(
        {
            "param_space": {"dimensions": [{"name": "a", "values": [1, 2]}]},
            "critical_paths": ["out/x.json"],
            "plugin": {"command": "echo {OUT}"},
            "workdir": "./w",
            "output": "./o",
        }
    )
    assert isinstance(cfg, Config)
    assert cfg.space.size == 2
    assert cfg.critical_paths == ["out/x.json"]
    assert cfg.plugin_command == "echo {OUT}"
    assert cfg.param_keys() == ["a"]


def test_load_config_plugin_as_string():
    cfg = load_config(
        {
            "dimensions": [{"name": "a", "values": [1]}],
            "plugin": "run.py --out {OUT}",
            "timeout": 5,
        }
    )
    assert cfg.plugin_command == "run.py --out {OUT}"
    assert cfg.timeout == 5.0


def test_load_config_default_paths_and_auto_rollback():
    cfg = load_config(
        {"dimensions": [{"name": "a", "values": [1]}], "plugin": {"command": "true {OUT}"}}
    )
    assert cfg.workdir == Path("work")
    assert cfg.output == Path("output")
    assert cfg.auto_rollback is True


def test_load_config_rejects_bad_critical_paths():
    with pytest.raises(ConfigError):
        load_config(
            {"dimensions": [{"name": "a", "values": [1]}], "critical_paths": "not-a-list"}
        )


def test_load_config_yaml_requires_pyyaml(tmp_path):
    pytest.importorskip("yaml")
    import yaml

    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({
        "dimensions": [{"name": "a", "values": [1, 2]}],
        "plugin": {"command": "echo {OUT}"},
    }))
    cfg = load_config(p)
    assert cfg.space.size == 2


def test_load_config_rejects_empty_command():
    with pytest.raises(ConfigError):
        load_config({"dimensions": [{"name": "a", "values": [1]}]})


def test_load_config_rejects_command_without_out():
    with pytest.raises(ConfigError):
        load_config(
            {"dimensions": [{"name": "a", "values": [1]}],
             "plugin": {"command": "echo hello"}}
        )


def test_load_config_root_must_be_mapping():
    with pytest.raises(ConfigError):
        load_config("[1, 2, 3]")  # a JSON list, not a mapping


def test_load_config_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does_not_exist.json")


def test_load_config_invalid_json_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not valid json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_load_config_identity_shortcut():
    cfg = load_config(
        {"dimensions": [{"name": "a", "values": [1]}], "plugin": {"command": "true {OUT}"}}
    )
    assert load_config(cfg) is cfg


def test_load_config_timeout_from_plugin_dict():
    cfg = load_config(
        {
            "dimensions": [{"name": "a", "values": [1]}],
            "plugin": {"command": "true {OUT}", "timeout": 7},
        }
    )
    assert cfg.timeout == 7.0


def test_load_config_plugin_timeout_overrides_top_level():
    cfg = load_config(
        {
            "dimensions": [{"name": "a", "values": [1]}],
            "plugin": {"command": "true {OUT}", "timeout": 7},
            "timeout": 3,
        }
    )
    assert cfg.timeout == 7.0  # explicit plugin.timeout wins over top-level
