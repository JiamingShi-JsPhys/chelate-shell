"""task-organizer scripts package.

Core modules:
- scan: recursive directory scan with type/hidden/empty classification.
- snapshot: before/after SHA256 snapshots for mandatory verification.
- organize: standard three-tier structure creation and file placement.
- verify: mandatory before/after verification with rollback trigger.
- dedupe: exact + similarity duplicate detection.
- history: operation history with undo/redo.
- rules: optional YAML placement-rule configuration (with named profiles).
- index_md / index_xlsx: Index.md / Index.xlsx generation.
- rollback: reverse operations from the move log, restore before state.
- utils: shared helpers (path, file, logging, AI-summary, structure).
- text_extract: plain-text extraction for txt/md/csv/json/docx/pdf/pptx/xlsx.
- broadcast: the context-compression index ("broadcast center", _broadcast/).
- init: lightweight skeleton creation (the cheap counterpart to organize).
- sources: file-provenance manifest (user material vs. assistant downloads).
- hashcache: mtime+size digest cache powering the incremental tier.
- rotate: automatic rotation of process/ artifacts.
"""

__all__ = [
    "scan",
    "snapshot",
    "organize",
    "verify",
    "dedupe",
    "history",
    "rules",
    "index_md",
    "index_xlsx",
    "rollback",
    "init",
    "sources",
    "hashcache",
    "rotate",
    "utils",
    "text_extract",
    "broadcast",
]

__version__ = "1.2.0"
