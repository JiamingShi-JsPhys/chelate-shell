#!/usr/bin/env python3
"""Sample compute plugin for multi-dim-manager.

This file demonstrates the plugin contract the manager relies on:

  * Read the round parameters from the file named by ``--params`` (JSON).
  * Write the result to the file named by ``--out`` (JSON).
  * Exit 0 on success, 1 if a check fails, 2 on an unexpected error.

Replace the marked block with your real computation (LMM fitting, symbolic
verification, group classification, ...). The manager never looks inside the
computation; it only records the contract outcome (exit code, output file,
hashes). Deterministic output (same params -> same result) is the plugin's
responsibility, not the manager's.
"""

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True, help="path to parameter JSON")
    ap.add_argument("--out", required=True, help="path to write result JSON")
    args = ap.parse_args()

    params = json.loads(Path(args.params).read_text(encoding="utf-8"))

    # --- begin domain computation (replace with your own) ---
    numeric = [v for v in params.values() if isinstance(v, (int, float))]
    score = sum(numeric) if numeric else len(params)
    result = {
        "received": params,
        "score": score,
        "ok": True,
    }
    # --- end domain computation ---

    Path(args.out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
