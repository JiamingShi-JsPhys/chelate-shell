"""Audit: 1.0.0 SKILL.md documented commands vs v1.1.0 tree.

Compares every legacy skill's documented python entrypoints between the
1.0.0 reference tree and the v1.1.0 tree, then verifies each legacy entry
module is still importable inside the v1.1.0 tree. Exits non-zero if any
documented entrypoint disappeared or any legacy module fails to import.

The 1.0.0 reference tree is located via CHELATE_V100_SRC (default:
../chelate-shell-main, resolved from this script's location).
"""
import importlib
import os
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
SKILLS = REPO / "skills"

LEGACY = [
    "task-organizer", "multi-dim-manager", "document-evolution-tracker",
    "capstone-labmate", "video-tracker", "longitudinal-analysis",
    "formula-validator", "ai-trace-remover", "conflict-detector",
]

env_src = os.environ.get("CHELATE_V100_SRC")
src = pathlib.Path(env_src) if env_src else REPO.parent / "chelate-shell-main" / "skills"
src = src.resolve()

pat = re.compile(r"python[^\n|`]*?(?:scripts|src)[./][\w./-]+")
total_src = total_dst = 0
missing_any = False

if not src.is_dir():
    print(f"reference tree not found: {src}")
    print("set CHELATE_V100_SRC to the 1.0.0 skills directory to run this audit")
    sys.exit(2)

for s in LEGACY:
    a = (src / s / "SKILL.md").read_text(encoding="utf-8")
    b = (SKILLS / s / "SKILL.md").read_text(encoding="utf-8")
    cmds_a = {m.strip() for m in pat.findall(a)}
    cmds_b = {m.strip() for m in pat.findall(b)}
    missing = cmds_a - cmds_b
    total_src += len(cmds_a)
    total_dst += len(cmds_b)
    state = "identical" if a == b else "differs"
    line = f"{s:28} SKILL.md {state:9} | entrypoints {len(cmds_a)} -> {len(cmds_b)}"
    if missing:
        missing_any = True
        line += f"  MISSING: {sorted(missing)}"
    print(line)
print(f"\nTOTAL documented python entrypoints: {total_src} (1.0.0) -> {total_dst} (v1.1.0)")

# Functional CLI inventory: every legacy entry module still importable
print("\n--- legacy entry modules importable in v1.1.0 tree ---")
entries = [
    ("task-organizer", "scripts.run"),
    ("multi-dim-manager", "scripts.run"),
    ("document-evolution-tracker", "src.cli"),
    ("capstone-labmate", "scripts.preconfigure_cap"),
    ("capstone-labmate", "scripts.process_cap"),
    ("capstone-labmate", "scripts.draft_report"),
    ("video-tracker", "scripts.run"),
    ("longitudinal-analysis", "src.cli"),
    ("formula-validator", "scripts.cli"),
    ("ai-trace-remover", "src.cli"),
    ("conflict-detector", "src.cli"),
]
ok = fail = 0
for skill, mod in entries:
    p = subprocess.run(
        [sys.executable, "-c", f"import importlib; importlib.import_module('{mod}')"],
        cwd=str(SKILLS / skill), capture_output=True, text=True)
    if p.returncode == 0:
        ok += 1
        print(f"  OK   {skill:24} {mod}")
    else:
        fail += 1
        print(f"  FAIL {skill:24} {mod}: {p.stderr.strip().splitlines()[-1][:100]}")
print(f"\nimportable: {ok}/{len(entries)}")

sys.exit(1 if (missing_any or fail) else 0)
