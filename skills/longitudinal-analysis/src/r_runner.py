"""Rscript runner for the statistical steps (LMM, mediation, sensitivity).

The runner hands a JSON payload over stdin to an Rscript and reads a JSON
result back from stdout. It degrades gracefully: when ``Rscript`` is not on
``PATH`` the function raises :class:`RNotAvailableError` so the pipeline can
skip R-backed steps and still emit the pure-Python ones.

Pure standard library.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional

__all__ = [
    "PluginResult",
    "RNotAvailableError",
    "run_r",
    "has_rscript",
]


class RNotAvailableError(RuntimeError):
    """Raised when ``Rscript`` is not found on the system PATH."""


@dataclass
class PluginResult:
    """Captured result of a subprocess invocation."""

    exit_code: int
    stdout: str
    stderr: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def has_rscript() -> bool:
    """Return True if an ``Rscript`` executable is reachable on PATH."""
    return shutil.which("Rscript") is not None


def run_r(
    script: str,
    payload: Dict[str, Any],
    timeout: int = 600,
    rscript_bin: Optional[str] = "Rscript",
) -> Dict[str, Any]:
    """Run an R script with a JSON payload on stdin; return parsed stdout.

    Parameters
    ----------
    script:
        Path to the ``.R`` file to execute.
    payload:
        Mapping serialised to JSON and written to the script's stdin.
    timeout:
        Wall-clock seconds before the subprocess is killed.
    rscript_bin:
        Override the interpreter (default: ``Rscript``).

    Returns
    -------
    dict
        The JSON value the R script wrote to stdout.

    Raises
    ------
    RNotAvailableError
        If no ``Rscript`` binary is available.
    RuntimeError
        If the R script exits non-zero.
    """

    if not has_rscript() and rscript_bin in ("Rscript", None):
        raise RNotAvailableError(
            "Rscript not found on PATH; install R >= 4.0 to run this step"
        )

    proc = subprocess.run(
        [rscript_bin or "Rscript", str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"R script failed: {proc.stderr.strip()}")
    text = proc.stdout.strip()
    if not text:
        return {}
    return json.loads(text)
