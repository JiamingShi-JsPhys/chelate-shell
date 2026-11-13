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
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Union

from .common import sha256
from .errors import PluginError

_NO_OUTPUT = b"NO_OUTPUT"

# Characters that only mean something to a shell. The plugin is executed
# without one, so these would be handed to the plugin as literal arguments and
# quietly change the meaning of the command; refusing them is more honest than
# pretending shell syntax still works.
_SHELL_OPERATOR_CHARS = ";&|<>`"


def split_plugin_command(template: str) -> List[str]:
    """Split a command template into an argv list without invoking a shell.

    Quoting follows POSIX rules everywhere except Windows, where ``shlex`` in
    POSIX mode would treat ``\\`` as an escape character and corrupt paths
    such as ``C:\\data\\plugin.py``. On Windows the non-POSIX tokenizer keeps
    backslashes intact and the surrounding quotes are stripped afterwards.
    """
    if os.name == "nt":
        tokens = shlex.split(template, posix=False)
        stripped: List[str] = []
        for tok in tokens:
            if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ("'", '"'):
                tok = tok[1:-1]
            stripped.append(tok)
        return stripped
    return shlex.split(template)


def _find_shell_operator(template: str) -> Optional[str]:
    """Return the first unquoted shell operator in *template*, if any.

    A character scan rather than a token check: Windows' non-POSIX tokenizer
    keeps ``;`` glued to the preceding word (``hi;``), so a token-level test
    would miss ``echo hi; rm -rf {OUT}`` on exactly the platform this guard
    exists for.
    """
    quote: Optional[str] = None
    i, n = 0, len(template)
    while i < n:
        ch = template[i]
        if quote:
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"' and os.name != "nt":
                i += 2
                continue
        elif ch in ("'", '"'):
            quote = ch
        elif ch in _SHELL_OPERATOR_CHARS:
            return ch
        i += 1
    return None


def _checked_argv(template: str) -> List[str]:
    """Tokenize *template*, rejecting shell-only syntax with a clear error."""
    operator = _find_shell_operator(template)
    if operator:
        raise PluginError(
            f"plugin command contains the shell operator {operator!r}; "
            "commands run without a shell. Put the pipeline in a script and "
            "point the template at it, or configure plugin.command as a list "
            "of arguments."
        )
    argv = split_plugin_command(template)
    if not argv:
        raise PluginError("plugin command is empty")
    return argv


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
    plugin_command: Union[str, Sequence[str]],
    workdir: Path,
    out_dir: Path,
    timeout: Optional[float] = None,
) -> ExecutionResult:
    """Execute the plugin for *round_no* and capture its contract outcome.

    Args:
        round_no: 1-based round index.
        params: The parameter combination for this round.
        plugin_command: Command template containing ``{PARAMS}``/``{OUT}``,
            given either as a string (split without a shell, honouring
            quotes) or as a ready-made argument list.
        workdir: Directory the plugin runs in (and reads/writes).
        out_dir: Directory for manager-side param/result files.
        timeout: Optional wall-clock timeout in seconds.

    Returns:
        An :class:`ExecutionResult`.

    Raises:
        PluginError: If the command template has no ``{OUT}`` placeholder, uses
            shell-only syntax (``|``, ``&&``, ``>``, ...), or the subprocess
            times out. A missing executable is not raised: it is recorded as
            exit code 127, the same outcome a shell would have produced.
    """
    workdir = Path(workdir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir.mkdir(parents=True, exist_ok=True)

    template = (plugin_command if isinstance(plugin_command, str)
                else " ".join(str(part) for part in plugin_command))
    if "{OUT}" not in template:
        raise PluginError("plugin command must contain the {OUT} placeholder")
    # {PARAMS} is optional (a plugin may read env instead), but we always
    # provide the file so behaviour is uniform.
    params_file = out_dir / f"params_round{round_no:04d}.json"
    out_file = out_dir / f"out_round{round_no:04d}.json"
    params_file.write_text(
        json.dumps(params, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    # Substitute per token, after splitting: a workspace path containing a
    # space then stays a single argument instead of being torn in two.
    argv = [
        tok.replace("{PARAMS}", str(params_file)).replace("{OUT}", str(out_file))
        for tok in _checked_argv(template)
    ]
    # The audit hash is taken over the substituted template, not over argv, so
    # hashes recorded by earlier releases remain comparable.
    command = template.replace("{PARAMS}", str(params_file)).replace(
        "{OUT}", str(out_file))

    try:
        proc = subprocess.run(
            argv,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing
        raise PluginError(f"plugin timed out after {timeout}s") from exc
    except FileNotFoundError:
        exit_code, stdout = 127, ""
        stderr = f"executable not found: {argv[0]}"

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
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        result_data=result_data,
        input_hash=sha256(input_blob),
        output_hash=sha256(output_blob),
    )
