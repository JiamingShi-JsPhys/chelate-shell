"""Pipeline orchestration: read the dataset, run enabled steps, audit everything.

Each step is dispatched to its module by type. R-backed steps (lmm,
mediation, sensitivity) are wrapped so a missing R installation degrades
gracefully (skipped + logged) instead of crashing the whole pipeline.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

import pandas as pd

from . import audit
from .config import AnalysisConfig
from .r_runner import RNotAvailableError
from .steps import descriptive, lmm, manipulation, mediation, sensitivity

__all__ = [
    "run_pipeline",
    "run_step",
]

# Step type -> module that implements :func:`run_step`.
_DISPATCH = {
    "descriptive": descriptive,
    "anova": manipulation,
    "lmm": lmm,
    "mediation": mediation,
    "sensitivity": sensitivity,
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_step(step_type: str, name: str, df: pd.DataFrame, config: Dict[str, Any], cfg: AnalysisConfig) -> Union[Path, List[Path]]:
    """Run one step and return the path(s) it wrote (or a skip marker)."""
    module = _DISPATCH[step_type]
    return module.run(df, config, cfg)


def run_pipeline(cfg: AnalysisConfig, data_input: Union[str, Path] = None) -> Dict[str, Any]:
    """Execute the configured pipeline end-to-end and return a summary dict.

    Parameters
    ----------
    cfg:
        A validated :class:`AnalysisConfig`.
    data_input:
        Optional override of ``cfg.data_input`` (used by tests so the
        pipeline can run against a fixture CSV without editing the config).

    Returns
    -------
    dict
        ``{"analysis_id", "log_path", "steps": [ {step, status, output, ...} ]}``
    """
    audit.set_seed(cfg.seed)

    input_path = Path(data_input) if data_input is not None else cfg.data_input
    df = pd.read_csv(input_path)

    logs_dir = Path(cfg.outputs["logs"])
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "analysis_log.jsonl"

    summary: Dict[str, Any] = {
        "analysis_id": cfg.analysis_id,
        "log_path": str(log_path),
        "steps": [],
    }

    with log_path.open("w", encoding="utf-8") as _fh:
        _fh.write("")  # truncate; the audit logger appends

    for step in cfg.steps:
        record = {"step": step.name, "started_at": _now()}
        if not step.enabled:
            record.update(status="skipped", reason="disabled")
            summary["steps"].append(record)
            continue
        try:
            out = run_step(step.type, step.name, df, step.config, cfg)
            record["output"] = [str(o) for o in out] if isinstance(out, list) else str(out)
            record["status"] = "success"
        except RNotAvailableError as exc:
            record["status"] = "skipped"
            record["reason"] = f"R unavailable: {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            record["status"] = "failed"
            record["reason"] = str(exc)
        record["finished_at"] = _now()
        summary["steps"].append(record)
        audit.log_step(
            step.name,
            {"seed": cfg.seed, "step": step.name},
            record,
            log_path,
        )

    return summary
