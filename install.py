"""Cross-host rule-file installer for Chelate Shell.

No agent host ships an installer that understands another host's rules, so
"install everywhere" cannot be delegated to any single vendor command. This
script is the one command that does it for this repository: it copies the
orchestrator contract into every supported host's rule location, in one run.

Two scopes:

    python install.py --project <dir>   project-scoped rules inside <dir>
    python install.py --global          user-scoped rules for detected hosts

`--project` writes the files a host reads from a project root (Cursor,
Windsurf, Cline, Continue, Roo Code, GitHub Copilot, and the generic
`AGENTS.md` that Codex, Cursor, Copilot agents and opencode all read).
`--global` writes the user-level rule files for hosts that document one:
opencode (`~/.config/opencode/AGENTS.md`), Codex (`$CODEX_HOME` or
`~/.codex`), and Claude Code (`~/.claude/CLAUDE.md`, only when `~/.claude`
already exists).

Plugin hosts (Claude Code, CodeBuddy, Codex, dsh) are *not* covered here:
their marketplace commands install the real plugin and preserve microkernel
auto-routing, which a rule file cannot do. See README "Installation".

Usage:
    python install.py --list
    python install.py --project . --dry-run
    python install.py --project .
    python install.py --global --only opencode,codex
    python install.py --project . --force

Caller: a user or agent running one command. No other file imports this
module; it is exercised as a subprocess.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# host key -> (destination relative to the project root, source file in repo)
PROJECT_RULES = {
    "cursor": (os.path.join(".cursor", "rules", "chelate-shell.mdc"),
               os.path.join(".cursor", "rules", "chelate-shell.mdc")),
    "windsurf": (os.path.join(".windsurf", "rules", "chelate-shell.md"),
                 os.path.join(".windsurf", "rules", "chelate-shell.md")),
    "cline": (os.path.join(".clinerules", "chelate-shell.md"),
              os.path.join(".clinerules", "chelate-shell.md")),
    "continue": (os.path.join(".continue", "rules", "chelate-shell.md"),
                 os.path.join(".continue", "rules", "chelate-shell.md")),
    "roo": (os.path.join(".roo", "rules", "chelate-shell.md"),
            os.path.join(".roo", "rules", "chelate-shell.md")),
    "copilot": (os.path.join(".github", "copilot-instructions.md"),
                os.path.join(".github", "copilot-instructions.md")),
    "agents": ("AGENTS.md", "AGENTS.md"),
}


def global_rules():
    """Return the user-scoped rule targets for this machine."""
    home = os.path.expanduser("~")
    return {
        "opencode": (os.path.join(home, ".config", "opencode", "AGENTS.md"),
                     "AGENTS.md"),
        "codex": (os.path.join(os.environ.get("CODEX_HOME") or
                               os.path.join(home, ".codex"), "AGENTS.md"),
                  "AGENTS.md"),
        "claude": (os.path.join(home, ".claude", "CLAUDE.md"), "AGENTS.md"),
    }


def _same(left_path: str, right_path: str) -> bool:
    try:
        with open(left_path, "rb") as left, open(right_path, "rb") as right:
            return left.read() == right.read()
    except OSError:
        return False


def _install(src_rel: str, dest: str, force: bool, dry_run: bool) -> str:
    """Copy one rule file; return 'wrote', 'unchanged' or 'skipped'."""
    src = os.path.join(REPO_ROOT, src_rel)
    if not os.path.isfile(src):
        raise SystemExit(f"install.py: missing source rule file: {src}")
    if os.path.isfile(dest) and _same(src, dest):
        return "unchanged"
    if os.path.isfile(dest) and not force:
        return "skipped"
    if dry_run:
        return "wrote"
    parent = os.path.dirname(dest) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".chelate-", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return "wrote"


def _select(only: str | None, keys) -> list:
    if not only:
        return list(keys)
    wanted = [part.strip() for part in only.split(",") if part.strip()]
    unknown = [w for w in wanted if w not in keys]
    if unknown:
        raise SystemExit("install.py: unknown host(s): " + ", ".join(unknown) +
                         "\nknown: " + ", ".join(keys))
    return wanted


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Copy the Chelate Shell rule file into every supported "
                    "agent host in one run.")
    parser.add_argument("--project", metavar="DIR",
                        help="install project-scoped rules into DIR")
    parser.add_argument("--global", dest="global_scope", action="store_true",
                        help="install user-scoped rules for detected hosts")
    parser.add_argument("--only", metavar="HOSTS",
                        help="comma-separated subset, e.g. cursor,opencode")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing rule file that differs")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be written, write nothing")
    parser.add_argument("--list", action="store_true",
                        help="show every host and its destination, then exit")
    args = parser.parse_args(argv)

    if args.list:
        print("project scope (--project DIR):")
        for key, (rel, _src) in PROJECT_RULES.items():
            print(f"  {key:<10} {rel}")
        print("global scope (--global), written only when the host is present:")
        for key, (dest, _src) in global_rules().items():
            state = "" if os.path.isdir(os.path.dirname(dest)) else "  (absent)"
            print(f"  {key:<10} {dest}{state}")
        return 0

    if not args.project and not args.global_scope:
        parser.error("choose --project DIR and/or --global (or --list)")

    results = []
    if args.project:
        project = os.path.abspath(args.project)
        os.makedirs(project, exist_ok=True)
        for key in _select(args.only, PROJECT_RULES):
            rel, src_rel = PROJECT_RULES[key]
            dest = os.path.join(project, rel)
            results.append((key, dest, _install(src_rel, dest, args.force,
                                                args.dry_run)))

    if args.global_scope:
        targets = global_rules()
        for key in _select(args.only, targets):
            dest, src_rel = targets[key]
            if not os.path.isdir(os.path.dirname(dest)):
                results.append((key, dest, "absent"))
                continue
            results.append((key, dest, _install(src_rel, dest, args.force,
                                                args.dry_run)))

    width = max(len(key) for key, _d, _s in results)
    for key, dest, state in results:
        print(f"  {key:<{width}}  {state:<9}  {dest}")

    wrote = sum(1 for _k, _d, s in results if s == "wrote")
    print(f"\n{wrote} file(s) written"
          + (" (dry run)" if args.dry_run else "")
          + ". Start a new session in the host to pick the rule up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
