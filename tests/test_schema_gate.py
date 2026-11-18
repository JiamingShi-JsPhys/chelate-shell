"""schema-gate: the contract is enforced, and an unknown keyword never passes."""
from __future__ import annotations

import json

import pytest

from lib.chelate_core import schema_check


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _csv(tmp_path, body):
    return _write(tmp_path, "data.csv", body)


SCHEMA = {
    "columns": {
        "time": {"type": "number", "required": True, "min": 0},
        "mass": {"type": "number", "required": False, "min": 0.0001},
        "label": {"type": "string", "allowed": ["a", "b"]},
    }
}


def test_a_clean_dataset_passes(tmp_path):
    columns, rows = schema_check.read_rows(
        _csv(tmp_path, "time,mass,label\n0,1.0,a\n1,2.5,b\n"))
    report = schema_check.check(SCHEMA, columns, rows)
    assert report["ok"] is True
    assert report["rows"] == 2
    assert report["checked_cells"] == 6


def test_a_missing_required_column_is_a_violation(tmp_path):
    columns, rows = schema_check.read_rows(_csv(tmp_path, "mass,label\n1,a\n"))
    report = schema_check.check(SCHEMA, columns, rows)
    kinds = {item["kind"] for item in report["violations"]}
    assert "missing-column" in kinds
    assert report["ok"] is False


def test_values_outside_the_contract_are_named_by_row(tmp_path):
    columns, rows = schema_check.read_rows(
        _csv(tmp_path, "time,mass,label\n-1,0.00001,c\nx,2.0,a\n"))
    report = schema_check.check(SCHEMA, columns, rows)
    by_kind = report["violations_by_kind"]
    assert by_kind["min"] >= 2          # time < 0 and mass < 0.0001
    assert by_kind["type"] == 1         # time = "x"
    assert by_kind["allowed"] == 1      # label = "c"
    assert report["violation_count"] == len(report["violations"])


def test_an_optional_column_may_be_empty(tmp_path):
    schema = {"columns": {"time": {"type": "number", "required": True},
                          "mass": {"type": "number", "required": False}}}
    columns, rows = schema_check.read_rows(_csv(tmp_path, "time,mass\n1,\n"))
    report = schema_check.check(schema, columns, rows)
    assert report["ok"] is True


def test_extra_columns_can_be_refused(tmp_path):
    strict = dict(SCHEMA, allow_extra_columns=False)
    columns, rows = schema_check.read_rows(
        _csv(tmp_path, "time,mass,label,secret\n0,1,a,x\n"))
    report = schema_check.check(strict, columns, rows)
    assert any(item["kind"] == "extra-column" for item in report["violations"])


def test_duplicate_csv_headers_are_reported(tmp_path):
    columns, rows = schema_check.read_rows(
        _csv(tmp_path, "time,time,mass\n0,1,2.0\n"))
    report = schema_check.check(SCHEMA, columns, rows)
    assert any(item["kind"] == "duplicate-column" for item in report["violations"])


def test_json_rows_are_read(tmp_path):
    path = _write(tmp_path, "rows.json", json.dumps(
        [{"time": 0, "mass": 1.0, "label": "a"},
         {"time": 1, "mass": None, "label": "b"}]))
    columns, rows = schema_check.read_rows(path)
    report = schema_check.check(SCHEMA, columns, rows)
    assert report["rows"] == 2
    assert report["ok"] is True


@pytest.mark.parametrize("schema, message", [
    ({"columns": {"a": {"type": "number", "minLength": 3}}}, "unsupported keyword"),
    ({"columns": {"a": {"type": "decimal"}}}, "unknown type"),
    ({"columns": {"a": {"pattern": "["}}}, "does not compile"),
    ({"columns": {}}, "non-empty"),
    ({"columns": {"a": {}}, "extra": 1}, "unknown top-level"),
    ({"colums": {"a": {}}}, "unknown top-level"),
])
def test_a_schema_this_validator_cannot_check_is_refused(schema, message):
    with pytest.raises(schema_check.SchemaError, match=message):
        schema_check.validate_schema(schema)


def test_boolean_accepts_only_true_and_false(tmp_path):
    schema = {"columns": {"flag": {"type": "boolean"}}}
    columns, rows = schema_check.read_rows(_csv(tmp_path, "flag\ntrue\nmaybe\n"))
    report = schema_check.check(schema, columns, rows)
    assert report["violations_by_kind"]["type"] == 1
