"""Tests for param_space parsing and expansion."""

import json

import pytest

from scripts.param_space import (
    Dimension,
    ParamSpace,
    expand,
    load_space,
)
from scripts.errors import ConfigError


def test_dimension_requires_name_and_values():
    with pytest.raises(ConfigError):
        Dimension(name="", values=[1])
    with pytest.raises(ConfigError):
        Dimension(name="x", values=[])


def test_space_size_is_cartesian():
    space = ParamSpace(
        dimensions=(
            Dimension("a", (1, 2)),
            Dimension("b", ("x", "y", "z")),
        )
    )
    assert space.size == 6
    assert space.names == ["a", "b"]


def test_combinations_yields_all():
    space = ParamSpace(
        dimensions=(
            Dimension("a", (1, 2)),
            Dimension("b", ("x", "y")),
        )
    )
    combos = list(space.combinations())
    assert len(combos) == 4
    assert {"a": 1, "b": "x"} in combos
    assert {"a": 2, "b": "y"} in combos


def test_load_space_from_dict():
    space = load_space({"param_space": {"dimensions": [{"name": "k", "values": [1, 2, 3]}]}})
    assert space.size == 3


def test_load_space_from_json_string():
    raw = json.dumps({"dimensions": [{"name": "m", "values": [1, 2]}]})
    space = load_space(raw)
    assert space.size == 2


def test_load_space_rejects_empty_dimensions():
    with pytest.raises(ConfigError):
        load_space({"dimensions": []})


def test_load_space_yaml_requires_pyyaml(tmp_path):
    pytest.importorskip("yaml")
    import yaml

    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"dimensions": [{"name": "m", "values": [1, 2]}]}))
    space = load_space(p)
    assert space.size == 2


def test_expand_helper():
    out = expand({"dimensions": [{"name": "a", "values": [1, 2]}, {"name": "b", "values": [3]}]})
    assert out == [{"a": 1, "b": 3}, {"a": 2, "b": 3}]


def test_space_from_raw_requires_name():
    with pytest.raises(ConfigError):
        load_space({"dimensions": [{"values": [1, 2]}]})


def test_space_from_raw_requires_list_values():
    with pytest.raises(ConfigError):
        load_space({"dimensions": [{"name": "a", "values": "not-a-list"}]})
    with pytest.raises(ConfigError):
        load_space({"dimensions": [{"name": "a", "values": []}]})


def test_load_space_from_path(tmp_path):
    p = tmp_path / "space.json"
    p.write_text(json.dumps({"dimensions": [{"name": "k", "values": [1, 2, 3]}]}),
                 encoding="utf-8")
    assert load_space(p).size == 3


def test_load_space_invalid_json_file(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_space(p)
