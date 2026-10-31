# Per-skill dependencies (1.2.0)

Declared in each skill's `manifest.json` and enforced at run time by
`core/sandbox.py`. A missing required dependency degrades that one
skill to an `UNVERIFIED` gate; it never crashes the pipeline.

| Skill | Required dependencies | Optional (degrade gracefully) |
|-------|----------------------|------------------------------|
| ai-trace-remover | *(stdlib only)* | — |
| bibtex-normalizer | `bibtexparser` | — |
| capstone-labmate | *(stdlib only)* | numpy (vectorized paths), matplotlib (plots), pypdf (PDF text) |
| conflict-detector | *(stdlib only)* | PyYAML (`.yaml` configs; JSON configs need nothing) |
| data-profiler | `pandas` | — |
| document-evolution-tracker | *(stdlib only)* | PyYAML (`.yaml` configs; JSON configs need nothing) |
| figure-generator | `matplotlib`, `seaborn`, `pandas` | — |
| formula-validator | sympy, numpy, pint | — |
| fulltext-extractor | pdfminer.six / pypdf | — |
| latex-exporter | *(stdlib only)* | — |
| literature-retriever | `arxiv` | — |
| longitudinal-analysis | pandas | numpy, R (lme4/lavaan), python-docx (`--format docx` export), PyYAML (`.yaml` configs) |
| ml-auditor | `scikit-learn`, `pandas` | `cleanlab` (second-opinion label issues) |
| multi-dim-manager | *(stdlib only)* | PyYAML (`.yaml` configs; JSON configs need nothing) |
| quantitative-validator | `rdkit` | — |
| reference-auditor | `requests` | — |
| task-organizer | *(stdlib only)* | openpyxl (fast `.xlsx` path), PyPDF2 (one PDF backend) |
| video-tracker | numpy, opencv | matplotlib (FFT plots), PyYAML (`.yaml` configs) |

Third-party packages are imported at run time only; none are vendored
into this repository, and each stays under its own permissive licence
(numpy/pandas BSD, OpenCV Apache-2.0, SymPy/pint/requests/bibtexparser/
arxiv BSD/MIT/Apache, pdfminer.six MIT, pypdf BSD-3-Clause).
