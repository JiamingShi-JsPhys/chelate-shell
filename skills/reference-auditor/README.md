# reference-auditor

Verify every DOI in a draft manuscript against the Crossref REST API. A
non-existent DOI is a hard gate failure that terminates the pipeline —
intermediate products stay locked in `process/`.

Part of [Chelate Shell](../../README.md) (MIT). The AI-facing instructions
live in [SKILL.md](SKILL.md); the Router contract lives in
[manifest.json](manifest.json).

## Install

```bash
pip install requests
```

## Usage

```bash
python run.py --root <workspace> --action audit --input draft.md
python run.py --root <workspace> --action audit --text "see https://doi.org/10.9999/fake"
```

The per-DOI HTTP timeout comes from `assets/config.yaml` (default 20 s).

## Outputs

| Path | Content |
|------|---------|
| `process/reference_audit_<stamp>.json` | per-DOI verdicts: status, title, container, year, HTTP status |
| `process/gates/reference-auditor_<ts>.json` | gate result |

## Gate semantics

- **PASS** — every DOI resolves (HTTP 200), EXACT evidence.
- **FAIL** — at least one DOI returns 404; the reason names the offenders.
  The Router terminates the pipeline immediately.
- **UNVERIFIED** — network/API failure for all DOIs, or no DOIs found
  (nothing to audit).

## Design

`run.py` is a thin adapter; DOI extraction (conservative regex) and
Crossref verification live in
[`lib/chelate_core/doi_audit.py`](../../lib/chelate_core/doi_audit.py).
No API key is used — only the public API with a politeness `mailto`.

## License

MIT — see [LICENSE](LICENSE).
