"""Recipes — a named, ordered list of registered skills.

Caller: `core.runtime.Runtime.start_recipe`, and `cli.py recipe`.
Data schemas:
    Reads:  <workspace>/recipes/<name>.json
            {"name": "paper-review",
             "description": "optional, one line",
             "stop_on_fail": true,
             "steps": [{"skill": "fulltext-extractor",
                        "args": ["--input", "inbox/paper.pdf"]}]}
    Writes: none of its own. Each step writes what that skill writes —
            `process/` only.
Design: serial in v1, DAG-shaped data.

    The step list is stored as a graph (`graph()` returns nodes and the
    edges implied by order) so that parallel execution in 1.5.0 does not
    need a new file format. Edges are consecutive by definition here: a
    step's dependencies are the steps before it. Nothing in the file can
    name an arbitrary predecessor, which is why `graph()` is derivable
    rather than stored — a stored edge list is a second source of truth that
    can disagree with the order.

    What a recipe deliberately cannot say:

    * a skill that is not in the registry — checked at load, against the
      same registry the router uses;
    * a copy, move, shell or write step. There is no verb for it. A step is
      a skill name and arguments; anything that looks like an action is
      rejected as an unknown key rather than ignored;
    * `publish`. Every step runs with `publish=False`: a recipe produces
      into `process/`, and publishing is a separate, approved act. A recipe
      that promoted on every step would ask a human for the same decision
      once per skill.

    A failed step stops the recipe by default (`stop_on_fail`), because the
    later steps were written assuming the earlier ones produced their
    output; running them anyway turns one failure into a cascade of
    misleading ones.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core import hooks as hooks_mod
from core import runtime as runtime_mod
from core.registry import load_default_registry

RECIPE_DIR = "recipes"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOP_KEYS = {"name", "description", "steps", "stop_on_fail"}
_STEP_KEYS = {"skill", "args"}


class RecipeError(ValueError):
    """The recipe cannot be loaded or must not run."""


@dataclass
class Step:
    skill: str
    args: List[str] = field(default_factory=list)


@dataclass
class Recipe:
    name: str
    steps: List[Step]
    description: str = ""
    stop_on_fail: bool = True
    path: str = ""


def recipe_dir(root: str) -> str:
    return os.path.join(os.path.abspath(root), RECIPE_DIR)


def names(root: str) -> List[str]:
    """Recipe names available in *root*, sorted; [] when there is no folder."""
    base = recipe_dir(root)
    if not os.path.isdir(base):
        return []
    return sorted(os.path.splitext(entry)[0] for entry in os.listdir(base)
                  if entry.endswith(".json"))


def load(root: str, name: str) -> Recipe:
    """Read one recipe. A name that could be a path is refused."""
    if not _NAME_RE.match(name or ""):
        raise RecipeError(f"recipe name {name!r} is not a plain file name")
    path = os.path.join(recipe_dir(root), f"{name}.json")
    if not os.path.isfile(path):
        raise RecipeError(f"no recipe {name!r} in {recipe_dir(root)}")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise RecipeError(f"recipes/{name}.json: {exc}") from exc
    if not isinstance(data, dict):
        raise RecipeError(f"recipes/{name}.json: expected an object")

    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise RecipeError(
            f"recipes/{name}.json: unknown key(s) {sorted(unknown)} — a step "
            f"that copies, moves or writes is not a recipe step")

    steps: List[Step] = []
    for index, raw in enumerate(data.get("steps") or []):
        if not isinstance(raw, dict):
            raise RecipeError(f"recipes/{name}.json: steps[{index}] is not an object")
        extra = set(raw) - _STEP_KEYS
        if extra:
            raise RecipeError(
                f"recipes/{name}.json: steps[{index}] has unknown key(s) "
                f"{sorted(extra)}")
        args = raw.get("args") or []
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise RecipeError(
                f"recipes/{name}.json: steps[{index}].args must be a list of strings")
        steps.append(Step(skill=str(raw.get("skill", "")), args=list(args)))

    stop_on_fail = data.get("stop_on_fail", True)
    if not isinstance(stop_on_fail, bool):
        raise RecipeError(f"recipes/{name}.json: stop_on_fail must be true or false")

    return Recipe(name=str(data.get("name") or name),
                  description=str(data.get("description") or ""),
                  steps=steps, stop_on_fail=stop_on_fail, path=path)


def validate(recipe: Recipe, registry=None) -> List[str]:
    """Every reason this recipe must not run. Empty == runnable."""
    registry = registry if registry is not None else load_default_registry()
    found: List[str] = []
    if not recipe.steps:
        found.append("a recipe with no steps does nothing")
    for index, step in enumerate(recipe.steps):
        if not step.skill:
            found.append(f"steps[{index}]: no skill named")
        elif step.skill not in registry:
            found.append(f"steps[{index}]: {step.skill!r} is not a registered skill")
    if recipe.name.split(".")[0] in {"", ".."}:
        found.append(f"recipe name {recipe.name!r} is not usable")
    return found


def graph(recipe: Recipe) -> Dict[str, Any]:
    """Nodes and the edges implied by step order (dag-shaped for 1.5.0)."""
    nodes = [{"id": f"step-{i}", "skill": s.skill, "args": list(s.args)}
             for i, s in enumerate(recipe.steps, 1)]
    edges = [[f"step-{i}", f"step-{i + 1}"] for i in range(1, len(nodes))]
    return {"recipe": recipe.name, "nodes": nodes, "edges": edges}


def plan(recipe: Recipe) -> List[Dict[str, Any]]:
    """What `run` would do, without doing it."""
    return [{"step": i, "skill": s.skill, "args": list(s.args)}
            for i, s in enumerate(recipe.steps, 1)]


def run(root: str, name: str, runtime=None) -> Dict[str, Any]:
    """Execute the recipe serially; publish nothing."""
    root = os.path.abspath(root)
    recipe = load(root, name)
    problems = validate(recipe)
    if problems:
        raise RecipeError("; ".join(problems))

    backend = runtime if runtime is not None else runtime_mod.select()
    hooks_mod.emit(root, "recipe_started",
                   {"recipe": recipe.name, "steps": len(recipe.steps)})

    outcomes: List[Dict[str, Any]] = []
    stopped_at: Optional[int] = None
    for index, step in enumerate(recipe.steps, 1):
        record: Dict[str, Any] = {"step": index, "skill": step.skill}
        try:
            result = backend.run_skill(root, step.skill, args=step.args,
                                       publish=False)
        except Exception as exc:  # a step may raise; the recipe still reports
            record.update({"ok": False, "error": f"{exc.__class__.__name__}: {exc}"})
            outcomes.append(record)
            stopped_at = index
            break
        failed = bool(result.get("terminated_by") or result.get("blocked"))
        record.update({
            "ok": not failed,
            "terminated_by": result.get("terminated_by"),
            "blocked": result.get("blocked"),
            "report": result.get("report"),
        })
        outcomes.append(record)
        hooks_mod.emit(root, "recipe_step", {"recipe": recipe.name, **record})
        if failed and recipe.stop_on_fail:
            stopped_at = index
            break

    completed = (len(outcomes) == len(recipe.steps)
                 and all(step.get("ok") for step in outcomes))
    report = {"recipe": recipe.name, "steps": outcomes, "completed": completed,
              "stopped_at": stopped_at, "promoted": False}
    hooks_mod.emit(root, "recipe_finished", report)
    return report
