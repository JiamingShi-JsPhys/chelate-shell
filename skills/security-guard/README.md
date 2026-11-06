# security-guard

Infrastructure gate for Chelate Shell.

- **Stage:** infrastructure
- **Type:** gate (anti-injection + AST static scan)
- **Dependencies:** none (standard library only)
- **License:** MIT

## What it does

Two independent gates implemented in `core/security_shield.py`:

1. **Anti-injection** (`scan_text`): inspects external text for high-confidence
   prompt-injection markers (e.g. "ignore previous instructions", `<|system|>`,
   "developer mode"). Conservative by design — legitimate scientific prose is
   never wrongly dropped. The pattern set is data, not code, so it is trivial
   to extend.
2. **AST static scan** (`scan_python_source` / `shield_report`): parses Python
   source and flags calls that can execute arbitrary code or spawn processes
   from untrusted input (`eval`, `exec`, `os.system`, `subprocess.*`,
   `pickle.loads`, `marshal.loads`). Import aliases are resolved so obfuscated
   call sites are still caught. A syntax error in the scanned source is itself
   reported as a violation, never silently swallowed.

## Usage

```bash
python run.py --root <WS> --action gate --input <FILE>
```

See `SKILL.md` for the full CLI contract. The adapter only wires the uniform
CLI (`--root` / `--action`) onto `core.security_shield`; all logic stays in
the core module.

## License

MIT — see [LICENSE](./LICENSE).
