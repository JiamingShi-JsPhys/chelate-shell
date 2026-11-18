"""Recipes: serial steps, no publishing, and no verbs that are not skills."""
from __future__ import annotations

import json
import os

import pytest

from core import recipes


def _write(root, name, payload):
    folder = os.path.join(str(root), "recipes")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return path


def _recipe(name="review", steps=None, **extra):
    payload = {"name": name, "steps": steps or [
        {"skill": "data-profiler", "args": ["--input", "inbox/a.csv"]},
        {"skill": "conflict-detector", "args": []},
    ]}
    payload.update(extra)
    return payload


def test_load_and_validate_a_working_recipe(workspace):
    _write(workspace, "review", _recipe())
    recipe = recipes.load(str(workspace), "review")
    assert [step.skill for step in recipe.steps] == [
        "data-profiler", "conflict-detector"]
    assert recipes.validate(recipe) == []


def test_names_lists_what_is_there(workspace):
    _write(workspace, "review", _recipe())
    assert recipes.names(str(workspace)) == ["review"]


def test_missing_folder_is_not_an_error(workspace):
    assert recipes.names(str(workspace)) == []


def test_unknown_top_level_key_is_refused(workspace):
    _write(workspace, "review", _recipe(copy=["a", "b"]))
    with pytest.raises(recipes.RecipeError, match="unknown key"):
        recipes.load(str(workspace), "review")


def test_a_step_cannot_invent_a_verb(workspace):
    _write(workspace, "review", {"name": "review", "steps": [
        {"skill": "data-profiler", "copy": "results/x"}]})
    with pytest.raises(recipes.RecipeError, match="unknown key"):
        recipes.load(str(workspace), "review")


def test_recipe_name_cannot_be_a_path(workspace):
    for bad in ("../escape", "a/b", ""):
        with pytest.raises(recipes.RecipeError):
            recipes.load(str(workspace), bad)


def test_unknown_skill_is_reported_before_anything_runs(workspace):
    _write(workspace, "review", _recipe(steps=[{"skill": "not-a-skill"}]))
    problems = recipes.validate(recipes.load(str(workspace), "review"))
    assert any("not a registered skill" in p for p in problems)


def test_empty_recipe_is_refused(workspace):
    _write(workspace, "review", {"name": "review", "steps": []})
    assert any("no steps" in p
               for p in recipes.validate(recipes.load(str(workspace), "review")))


def test_plan_and_graph_agree_on_the_order(workspace):
    _write(workspace, "review", _recipe())
    recipe = recipes.load(str(workspace), "review")
    plan = recipes.plan(recipe)
    graph = recipes.graph(recipe)
    assert [entry["skill"] for entry in plan] == [
        node["skill"] for node in graph["nodes"]]
    assert graph["edges"] == [["step-1", "step-2"]]


class FakeRuntime:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def run_skill(self, root, skill, args=None, **options):
        self.calls.append({"skill": skill, "args": args, "options": options})
        return self.results.pop(0)


def test_run_never_publishes_and_reports_every_step(workspace):
    _write(workspace, "review", _recipe())
    fake = FakeRuntime([{"promoted": False}, {"promoted": False}])
    report = recipes.run(str(workspace), "review", runtime=fake)
    assert report["completed"] is True
    assert report["promoted"] is False
    assert len(report["steps"]) == 2
    assert all(call["options"]["publish"] is False for call in fake.calls)


def test_a_failed_step_stops_the_recipe(workspace):
    _write(workspace, "review", _recipe())
    fake = FakeRuntime([{"terminated_by": "data-profiler"}])
    report = recipes.run(str(workspace), "review", runtime=fake)
    assert report["completed"] is False
    assert report["stopped_at"] == 1
    assert len(fake.calls) == 1


def test_stop_on_fail_false_runs_the_rest(workspace):
    _write(workspace, "review", _recipe(stop_on_fail=False))
    fake = FakeRuntime([{"terminated_by": "data-profiler"},
                        {"promoted": False}])
    report = recipes.run(str(workspace), "review", runtime=fake)
    assert len(fake.calls) == 2
    assert report["completed"] is False


def test_invalid_recipe_is_refused_before_the_first_step(workspace):
    _write(workspace, "review", _recipe(steps=[{"skill": "not-a-skill"}]))
    fake = FakeRuntime([])
    with pytest.raises(recipes.RecipeError):
        recipes.run(str(workspace), "review", runtime=fake)
    assert fake.calls == []
