"""document-evolution-tracker -- version alignment and concept lineage.

Given a family of document versions (a directory of timestamped / sequential
files, or a list of paths), this skill produces a paragraph-level diff
timeline and a concept-lineage graph. Pure standard library (``difflib`` /
``json`` / ``re``); no external dependencies.
"""

__version__ = "1.2.0"
