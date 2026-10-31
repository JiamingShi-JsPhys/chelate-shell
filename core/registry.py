"""Chelate Shell registry — scan skills/ and build an in-memory routing table.

Caller: core/router.py (imports registry), cli.py (bootstraps the registry),
        tests/core/test_registry.py.
No existing file in chelate-shell-v1.1.0/ serves this purpose.
Data schemas:
    Reads:  skills/<skill>/manifest.json for every direct child directory of
            skills/ (one level only — the physical tree is flat; nested
            namespace folders are NOT scanned and are reported as errors).
            Manifests are validated against contracts/schema.json semantics
            (required fields, stage enum, value types) with a pure-stdlib
            checker so the registry stays dependency-free.
    Writes: none (in-memory index only).
User instruction: "the engine scans every manifest.json under skills/ and loads
only the metadata (name, stage, dependencies) into memory to build a routing
table".

Design:
    - Lazy: only manifest metadata is read at scan time; SKILL.md is NOT loaded.
    - Each entry records: name, version, stage, dependencies, input_types,
      output_type, entrypoint, description, and the resolved run.py path.
    - The routing table is a dict[name] -> SkillRecord, plus a stage index for
      serial execution ordering.
    - Invalid manifests are skipped and recorded in `errors` (never fatal), so
      one broken skill cannot take down the whole registry.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

STAGES = ("workspace", "ingest", "gates", "processors")

_REQUIRED_FIELDS = ("name", "version", "stage", "input_types",
                    "output_type", "entrypoint", "description")
_STRING_FIELDS = ("name", "version", "stage", "output_type",
                  "entrypoint", "description")
_ARRAY_FIELDS = ("input_types", "dependencies", "output_types")
_BOOL_FIELDS = ("sandbox_required",)
_KNOWN_FIELDS = (set(_REQUIRED_FIELDS) | set(_ARRAY_FIELDS)
                 | set(_BOOL_FIELDS))


def validate_manifest(data: dict) -> List[str]:
    """Return a list of human-readable validation errors (empty == valid).

    Mirrors contracts/schema.json with a stdlib-only checker: jsonschema is
    an optional dependency and the registry must never require it.
    """
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["manifest is not a JSON object"]
    for key in _REQUIRED_FIELDS:
        if key not in data:
            errors.append(f"missing required field: {key}")
    for key in _STRING_FIELDS:
        if key in data and not isinstance(data[key], str):
            errors.append(f"field {key} must be a string")
    for key in _ARRAY_FIELDS:
        if key in data:
            value = data[key]
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"field {key} must be an array of strings")
    for key in _BOOL_FIELDS:
        if key in data and not isinstance(data[key], bool):
            errors.append(f"field {key} must be a boolean")
    stage = data.get("stage")
    if isinstance(stage, str) and stage not in STAGES:
        errors.append(f"field stage must be one of {list(STAGES)}, got {stage!r}")
    extra = sorted(set(data) - _KNOWN_FIELDS)
    if extra:
        errors.append(f"unknown fields not allowed by schema.json: {extra}")
    return errors


@dataclass
class SkillRecord:
    name: str
    version: str
    stage: str
    dependencies: List[str]
    input_types: List[str]
    output_type: str
    entrypoint: str
    description: str
    manifest_path: str
    run_path: str
    output_types: List[str] = field(default_factory=list)
    sandbox_required: bool = False

    @property
    def run_exists(self) -> bool:
        return os.path.isfile(self.run_path)

    def accepts(self, input_kind: str) -> bool:
        """True when this skill declares support for `input_kind`."""
        return (not input_kind) or (input_kind in self.input_types)


class Registry:
    """In-memory index of all discovered skills."""

    def __init__(self) -> None:
        self._by_name: Dict[str, SkillRecord] = {}
        self._by_stage: Dict[str, List[SkillRecord]] = {}
        self.errors: List[str] = []

    def scan(self, skills_dir: str) -> "Registry":
        base = pathlib.Path(skills_dir)
        if not base.is_dir():
            self.errors.append(f"skills directory not found: {skills_dir}")
            return self
        for manifest_path in sorted(base.glob("*/manifest.json")):
            self._load_one(manifest_path)
        nested = sorted(str(p) for p in base.glob("*/*/manifest.json"))
        for p in nested:
            self.errors.append(
                f"nested manifest forbidden by the flat-layout rule: {p}")
        return self

    def _load_one(self, manifest_path: pathlib.Path) -> None:
        skill_dir = manifest_path.parent
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            self.errors.append(f"{manifest_path}: unreadable JSON ({exc})")
            return
        problems = validate_manifest(data)
        if problems:
            for p in problems:
                self.errors.append(f"{manifest_path}: {p}")
            return
        name = data["name"]
        if name != skill_dir.name:
            self.errors.append(
                f"{manifest_path}: name {name!r} does not match directory "
                f"{skill_dir.name!r}")
            return
        entrypoint = data["entrypoint"]
        rec = SkillRecord(
            name=name,
            version=data["version"],
            stage=data["stage"],
            dependencies=list(data.get("dependencies", [])),
            input_types=list(data["input_types"]),
            output_type=data["output_type"],
            entrypoint=entrypoint,
            description=data["description"],
            manifest_path=str(manifest_path),
            run_path=str(skill_dir / entrypoint),
            output_types=list(data.get("output_types",
                                       [data["output_type"]])),
            sandbox_required=bool(data.get("sandbox_required", False)),
        )
        if not rec.run_exists:
            self.errors.append(f"{manifest_path}: entrypoint not found: {rec.run_path}")
            return
        if name in self._by_name:
            self.errors.append(f"{manifest_path}: duplicate skill name {name!r}")
            return
        self._by_name[name] = rec
        self._by_stage.setdefault(rec.stage, []).append(rec)

    def get(self, name: str) -> Optional[SkillRecord]:
        return self._by_name.get(name)

    def all(self) -> List[SkillRecord]:
        return sorted(self._by_name.values(), key=lambda r: r.name)

    def by_stage(self, stage: str) -> List[SkillRecord]:
        return sorted(self._by_stage.get(stage, []), key=lambda r: r.name)

    def by_input(self, input_kind: str,
                 stage: Optional[str] = None) -> List[SkillRecord]:
        """Skills that accept `input_kind`, optionally within one stage."""
        pool = self.by_stage(stage) if stage else self.all()
        return [r for r in pool if r.accepts(input_kind)]

    def names(self) -> List[str]:
        return sorted(self._by_name.keys())

    def __len__(self) -> int:
        return len(self._by_name)

    def __contains__(self, name: str) -> bool:
        return name in self._by_name


def load_default_registry(repo_root: Optional[str] = None) -> Registry:
    if repo_root is None:
        repo_root = str(pathlib.Path(__file__).resolve().parents[1])
    return Registry().scan(os.path.join(repo_root, "skills"))
