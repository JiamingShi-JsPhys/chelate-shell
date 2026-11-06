"""Chelate global core library — shared algorithms and adapter toolkit.

This package is the single home for cross-skill business logic (the
"programs live outside the skills" rule): skill folders stay thin and only
wire CLI arguments to these modules.

Layout:
    paths.py        repository / skill / workspace path resolution
    yamlmini.py     assets/config.yaml loader (PyYAML optional, degrades)
    adapter.py      thin-adapter toolkit: argparse helpers, gate emission,
                    legacy-CLI runner, controlled degradation
    pdf_text.py     PDF text extraction core (pdfminer.six)
    arxiv_search.py arXiv literature search core
    bibtex_norm.py  BibTeX parse / dedupe / normalize core
    doi_audit.py    DOI extraction + Crossref verification core
    csv_profile.py  CSV structural profiling core (pandas)
    formula_merge.py legacy D1-D5 verdict + pint unit layer merge policy

Nothing here imports from skills/; the dependency direction is always
skills/run.py -> lib/chelate_core/* -> (optional third-party packages).
"""
