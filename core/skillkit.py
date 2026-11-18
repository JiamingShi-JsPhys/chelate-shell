"""Scaffold and lint a skill — the two operations the tree keeps needing.

Caller: `cli.py skill new|lint`.
Data schemas:
    Reads:  skills/<name>/manifest.json, SKILL.md, README.md, LICENSE;
            CHANGELOG.md for the release note.
    Writes: a new skill folder (only `new`), and nothing else.

Why this exists: adding a skill means touching eleven places — manifest,
SKILL.md, README, LICENSE, the adapter, the shared library, tests, the count
in five documents, the file map. Half of them are mechanical and half are the
ones people forget. `new` writes the mechanical half from one template, and
`lint` fails on the forgotten half, which is cheaper than discovering it in a
release.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

STAGES = ("workspace", "ingest", "gates", "processors", "infrastructure",
          "generation", "domain_extensions")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
# Routing reads every skill description in every session, installed or not;
# a description that grows is a cost paid on every turn. The cap is loose
# enough for one sentence plus its trigger, and hard enough to stop drift.
DESCRIPTION_LIMIT = 120
# task-organizer's own suite pins the phrases that make its folder trigger
# fire ("named or attached", "whatever the deliverable", "however many
# steps"). Those phrases are the routing surface; the longer description is
# deliberate, and that test is the reason it may stay long.
DESCRIPTION_OVERRIDES = {"task-organizer": 420}


def frontmatter_description(text: str) -> str:
    """The SKILL.md `description`, folded when it is a `>` block scalar."""
    if not text.startswith("---"):
        return ""
    frontmatter = text.split("---", 2)[1]
    lines = frontmatter.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("description:"):
            continue
        value = line.split(":", 1)[1].strip()
        if value not in (">", "|"):
            return value
        block: List[str] = []
        for nxt in lines[index + 1:]:
            if nxt.strip() and not nxt.startswith(" "):
                break
            block.append(nxt.strip())
        return " ".join(block).strip()
    return ""
LICENSE_TEXT = """MIT License

Copyright (c) 2026 Jiaming Shi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


class SkillKitError(ValueError):
    """The name, stage or target directory cannot be used."""


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _adapter(name: str, description: str) -> str:
    """The thin-adapter skeleton — the same shape `test_no_stubs` expects."""
    return f'''"""{name} — thin adapter.

    python run.py --root <WS> --action run
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, next(
    (p for p in (_HERE, os.path.dirname(_HERE),
                 os.path.dirname(os.path.dirname(_HERE)),
                 os.path.dirname(os.path.dirname(os.path.dirname(_HERE))))
     if os.path.isdir(os.path.join(p, "lib", "chelate_core"))),
    os.path.abspath(os.path.join(_HERE, "..", ".."))))

from lib.chelate_core import adapter  # noqa: E402

SKILL = "{name}"
SKILL_ROOT = adapter.skill_root(__file__)
DEPENDENCIES = ()


def _configure(ap) -> None:
    ap.add_argument("--input", default="", help="input file")


def _run(args) -> dict:
    raise adapter.Degraded("not implemented yet: put the logic in "
                           "lib/chelate_core and call it from here")


HANDLERS = {{"run": _run}}

if __name__ == "__main__":
    sys.exit(adapter.dispatch(
        SKILL, _configure, HANDLERS, description={description!r}))
'''


def new(name: str, stage: str, version: str = "1.4.0",
        root: str = "", force: bool = False) -> Dict[str, Any]:
    """Write the mechanical half of a new skill; refuse anything ambiguous."""
    name = str(name or "").strip()
    if not NAME_RE.match(name):
        raise SkillKitError(
            f"{name!r} is not a skill name: lowercase letters, digits and "
            f"hyphens, 3-40 characters, no leading or trailing hyphen")
    if stage not in STAGES:
        raise SkillKitError(f"stage must be one of {list(STAGES)}, not {stage!r}")
    base = os.path.join(root or _repo_root(), "skills", name)
    if os.path.exists(base) and not force:
        raise SkillKitError(f"{base} already exists")

    description = f"{name} — say in one sentence what it decides or produces."
    manifest = {
        "name": name, "version": version, "stage": stage,
        "input_types": [], "output_type": "gate_result" if stage == "gates"
        else "artifact",
        "output_types": ["gate_result", "json"] if stage == "gates"
        else ["artifact"],
        "dependencies": [], "sandbox_required": False,
        "entrypoint": "run.py", "description": description,
    }
    os.makedirs(base, exist_ok=True)
    written = []

    def write(filename: str, text: str) -> None:
        path = os.path.join(base, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        written.append(filename)

    write("manifest.json", json.dumps(manifest, indent=2) + "\n")
    write("run.py", _adapter(name, description))
    write("LICENSE", LICENSE_TEXT)
    write("SKILL.md", f"""---
name: {name}
version: {version}
description: >
  {description}
metadata:
  version: {version}
  author: Jiaming Shi
  license: MIT
  entry_point: python run.py
  python_requires: '>=3.10'
---

# {name}

One paragraph: the question this skill answers, and the one it refuses to.

- **Stage:** `{stage}` · **Sandbox:** no · **Dependencies:** none

## Quick Execution

```bash
python run.py --root <WS> --action run --input data.csv
```

## Verdicts

| Status | When |
| --- | --- |
| `PASS` | … |
| `FAIL` | … |
| `UNVERIFIED` | … |

## When to use

- …

## When NOT to use

- …
""")
    write("README.md", f"""# {name}

{description}

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Usage

```bash
python run.py --root <workspace> --action run --input data.csv
```
""")
    return {"skill": name, "stage": stage, "path": base, "written": written,
            "next": ["write the logic in lib/chelate_core/",
                     "call it from run.py",
                     f"add `{name}` to tests/conftest.py ALL_SKILLS/STAGE_OF",
                     "add a CHANGELOG entry",
                     "run `python cli.py skill lint`"]}


def lint(root: str = "") -> Dict[str, Any]:
    """Every inconsistency a release would otherwise discover."""
    repo = root or _repo_root()
    skills = os.path.join(repo, "skills")
    changelog = ""
    changelog_path = os.path.join(repo, "CHANGELOG.md")
    if os.path.isfile(changelog_path):
        with open(changelog_path, encoding="utf-8") as fh:
            changelog = fh.read()
    problems: List[Dict[str, str]] = []
    missing_deps_note: List[str] = []

    def add(skill: str, problem: str) -> None:
        problems.append({"skill": skill, "problem": problem})

    names = sorted(d for d in os.listdir(skills)
                   if os.path.isdir(os.path.join(skills, d)))
    for name in names:
        folder = os.path.join(skills, name)
        manifest_path = os.path.join(folder, "manifest.json")
        if not os.path.isfile(manifest_path):
            add(name, "no manifest.json")
            continue
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except ValueError as exc:
            add(name, f"manifest.json is not JSON: {exc}")
            continue
        if manifest.get("name") != name:
            add(name, f"manifest name {manifest.get('name')!r} != folder")
        if manifest.get("stage") not in STAGES:
            add(name, f"stage {manifest.get('stage')!r} is not one of the "
                      f"declared stages")
        entry = str(manifest.get("entrypoint") or "run.py")
        if not os.path.isfile(os.path.join(folder, entry)):
            add(name, f"entrypoint {entry!r} does not exist")
        for required in ("SKILL.md", "README.md", "LICENSE"):
            if not os.path.isfile(os.path.join(folder, required)):
                add(name, f"missing {required}")
        skill_md = os.path.join(folder, "SKILL.md")
        if os.path.isfile(skill_md):
            with open(skill_md, encoding="utf-8") as fh:
                text = fh.read()
            declared = re.search(r"^name:\s*(\S+)", text, re.M)
            if not declared:
                add(name, "SKILL.md has no frontmatter name")
            elif declared.group(1) != name:
                add(name, f"SKILL.md name {declared.group(1)!r} != folder")
            if "## When NOT to use" not in text:
                add(name, "SKILL.md has no 'When NOT to use' section")
            for rel in re.findall(r"\]\((references/[^)\s#]+)", text):
                if not os.path.isfile(os.path.join(folder, rel)):
                    add(name, f"SKILL.md links {rel}, which does not exist")
            ref_dir = os.path.join(folder, "references")
            if os.path.isdir(ref_dir):
                for ref in sorted(os.listdir(ref_dir)):
                    if ref.endswith(".md") and \
                            f"references/{ref}" not in text:
                        add(name, f"references/{ref} is never linked from "
                                  f"SKILL.md")
            description = frontmatter_description(text)
            limit = DESCRIPTION_OVERRIDES.get(name, DESCRIPTION_LIMIT)
            if not description:
                add(name, "SKILL.md has no frontmatter description")
            elif len(description) > limit:
                add(name, f"SKILL.md description is {len(description)} chars; "
                          f"routing reads it every session (limit "
                          f"{limit})")
        if changelog and name not in changelog:
            missing_deps_note.append(name)
    return {"skills": len(names), "problems": problems,
            "not_in_changelog": missing_deps_note,
            "ok": not problems}
