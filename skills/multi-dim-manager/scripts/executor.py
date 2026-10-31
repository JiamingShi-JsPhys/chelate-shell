"""Invoke the user compute plugin for one round.

Plugin contract (fixed, see SKILL.md):
  * The manager writes the round parameters to a JSON file and substitutes its
    path for ``{PARAMS}`` in the command template.
  * The manager substitutes the path of an (initially empty) results file for
    ``{OUT}``; the plugin MUST write its results as JSON to that path.
  * The plugin exits with code 0 (success), 1 (asserted failure / check
    failed), or 2 (error / skipped).

The manager never interprets the computation; it only records the contract
outcome (exit code, output file, hashes).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .common import sha256
from .errors import PluginError

_NO_OUTPUT = b"NO_OUTPUT"


@dataclass
class ExecutionResult:
    """Outcome of running the plugin for one round."""

    round_no: int
    params: dict
    params_file: Path
    out_file: Path
    exit_code: int
    stdout: str
    stderr: str
    result_data: Optional[dict]
    input_hash: str
    output_hash: str

    @property
    def status(self) -> str:
        """Map the exit code to a stable status label."""
        if self.exit_code == 0:
            return "success"
        if self.exit_code == 1:
            return "failed"
        return "error"


def run_plugin(
    round_no: int,
    params: dict,
    plugin_command: str,
    workdir: Path,
    out_dir: Path,
    timeout: Optional[float] = None,
) -> ExecutionResult:
    """Execute the plugin for *round_no* and capture its contract outcome.

    Args:
        round_no: 1-based round index.
        params: The parameter combination for this round.
        plugin_command: Command template containing ``{PARAMS}``/``{OUT}``.
        workdir: Directory the plugin runs in (and reads/writes).
        out_dir: Directory for manager-side param/result files.
        timeout: Optional wall-clock timeout in seconds.

    Returns:
        An :class:`ExecutionResult`.

    Raises:
        PluginError: If the command template has no ``{OUT}`` placeholder, or
            the subprocess times out. (A missing executable is not raised here:
            with ``shell=True`` the OS shell reports it via a non-zero exit code,
            which the caller records as a failed/errored round.)
    """
    workdir = Path(workdir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    if "{OUT}" not in plugin_command:
        raise PluginError("plugin command must contain the {OUT} placeholder")
    # {PARAMS} is optional (a plugin may read env instead), but we always
    # provide the file so behaviour is uniform.
    params_file = out_dir / f"params_round{round_no:04d}.json"
    out_file = out_dir / f"out_round{round_no:04d}.json"
    params_file.write_text(
        json.dumps(params, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    if "{PARAMS}" in plugin_command:
        command = plugin_command.replace("{PARAMS}", str(params_file)).replace(
            "{OUT}", str(out_file)
        )
    else:
        command = plugin_command.replace("{OUT}", str(out_file))

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing
        raise PluginError(f"plugin timed out after {timeout}s") from exc

    result_data: Optional[dict] = None
    if out_file.exists():
        try:
            result_data = json.loads(out_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result_data = None

    input_blob = params_file.read_bytes() + command.encode("utf-8")
    output_blob = out_file.read_bytes() if out_file.exists() else _NO_OUTPUT
    return ExecutionResult(
        round_no=round_no,
        params=params,
        params_file=params_file,
        out_file=out_file,
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        result_data=result_data,
        input_hash=sha256(input_blob),
        output_hash=sha256(output_blob),
    )
