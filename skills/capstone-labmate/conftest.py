"""Pytest configuration: expose scripts/ to tests so modules import cleanly.

Each test file can `import process_cap`, `import draft_report`, `import _capx`
without depending on test working-directory.
"""
import sys
from pathlib import Path

# conftest.py lives at <skill-root>/conftest.py, scripts at <skill-root>/scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
