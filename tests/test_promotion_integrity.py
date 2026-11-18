"""What a promotion rests on: fresh gates, a complete copy, an honest hatch.

Three things changed in v1.3.6, and each one is written here as "the agent
tries X, the shell must not deliver it":

* a gate records the bytes it judged, so a PASS expires when they change;
* an UNVERIFIED gate — a check that could not be made — no longer carries a
  result into ``results/`` unless a person bound that decision to the token;
* the copy into ``results/`` is staged and renamed, so a crash leaves nothing
  half-published.

Plus one naming change: the scripted approval hatch is now called
``CHELATE_UNSAFE_AUTO_APPROVE``, because that is what it is.  The old name
still works and says so on stderr.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core import approval, router

STAMP = "20260101T000000Z"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _gate(ws: Path, skill: str, status: str = "PASS", inputs=None,
          digest: str = "") -> Path:
    payload = {"skill": skill, "status": status, "evidence_level": "EXACT",
               "reason": "stub", "artifacts": [],
               "timestamp": "2026-01-01T00:00:00Z"}
    if inputs is not None:
        payload["inputs"] = inputs
    if digest:
        payload["provenance"] = {"skill_version": "1.3.6",
                                 "skill_digest": digest,
                                 "gate_contract": 2}
    path = ws / "process" / "gates" / f"{skill}_20260101T000000Z.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _ws(tmp_path: Path, model: str = "H = sum(t * c_i c_j)") -> Path:
    ws = tmp_path / "ws"
    (ws / "material" / "initial").mkdir(parents=True)
    (ws / "process" / "gates").mkdir(parents=True)
    (ws / "material" / "initial" / "model.py").write_text(model,
                                                          encoding="utf-8")
    (ws / "process" / "bands.csv").write_text("k,E\n0,1.2\n", encoding="utf-8")
    return ws


# ------------------------------------------------------- gate freshness

def test_a_bound_gate_is_not_stale_while_its_input_is_unchanged(tmp_path):
    ws = _ws(tmp_path)
    rel = "material/initial/model.py"
    _gate(ws, "formula-validator", inputs={rel: _sha(
        (ws / rel).read_text(encoding="utf-8"))})

    assert router.stale_gates(str(ws)) == []
    assert router.gate_freshness(str(ws))["bound"] == 1
    assert router.promote(str(ws), STAMP) is not None


def test_editing_an_input_expires_the_gate_that_passed_on_it(tmp_path):
    """The agent changes the model after the check and asks to promote."""
    ws = _ws(tmp_path)
    rel = "material/initial/model.py"
    _gate(ws, "formula-validator",
          inputs={rel: _sha((ws / rel).read_text(encoding="utf-8"))})
    (ws / rel).write_text("H = 0  # not what was checked", encoding="utf-8")

    stale = router.stale_gates(str(ws))
    assert [s["skill"] for s in stale] == ["formula-validator"]
    assert rel in stale[0]["reason"]
    with pytest.raises(router.PromotionLocked) as exc:
        router.promote(str(ws), STAMP)
    assert "expired gate" in str(exc.value)
    assert not list((ws / "results").glob("promoted_*"))


def test_deleting_a_bound_input_expires_the_gate(tmp_path):
    ws = _ws(tmp_path)
    rel = "material/initial/model.py"
    _gate(ws, "formula-validator",
          inputs={rel: _sha((ws / rel).read_text(encoding="utf-8"))})
    (ws / rel).unlink()

    assert "missing" in router.stale_gates(str(ws))[0]["reason"]
    with pytest.raises(router.PromotionLocked):
        router.promote(str(ws), STAMP)


def test_rerunning_the_skill_clears_the_expiry(tmp_path):
    ws = _ws(tmp_path)
    rel = "material/initial/model.py"
    _gate(ws, "formula-validator",
          inputs={rel: _sha((ws / rel).read_text(encoding="utf-8"))})
    (ws / rel).write_text("H = 0", encoding="utf-8")
    assert router.stale_gates(str(ws))

    # A newer gate — what re-running the skill writes — describes the file
    # on disk now, so the workspace is promotable again.
    newer = ws / "process" / "gates" / "formula-validator_20260101T000100Z.json"
    newer.write_text(json.dumps({
        "skill": "formula-validator", "status": "PASS",
        "evidence_level": "EXACT", "reason": "re-run",
        "timestamp": "2026-01-01T00:01:00Z",
        "inputs": {rel: _sha("H = 0")},
    }), encoding="utf-8")
    assert router.stale_gates(str(ws)) == []
    assert router.promote(str(ws), STAMP) is not None


def test_a_gate_from_before_136_is_unbound_not_trusted(tmp_path):
    """Old gates carry no digests; they are counted, not called fresh."""
    ws = _ws(tmp_path)
    _gate(ws, "data-profiler")

    freshness = router.gate_freshness(str(ws))
    assert freshness["unbound"] == 1
    assert freshness["bound"] == 0
    assert freshness["unbound_skills"] == ["data-profiler"]
    assert router.stale_gates(str(ws)) == []


def test_a_pass_whose_skill_code_changed_is_stale(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    _gate(ws, "formula-validator", digest="0" * 32)
    monkeypatch.setattr(router, "_current_skill_digest",
                        lambda _skill: "1" * 32)

    stale = router.stale_gates(str(ws))
    assert [s["skill"] for s in stale] == ["formula-validator"]
    assert "skill code" in stale[0]["reason"]


# ------------------------------------------------- unverified gates

def test_an_unverified_gate_blocks_promotion_by_default(tmp_path):
    ws = _ws(tmp_path)
    _gate(ws, "quantitative-validator", status="UNVERIFIED")

    with pytest.raises(router.PromotionLocked) as exc:
        router.promote(str(ws), STAMP)
    assert "unverified gate" in str(exc.value)
    assert "--allow-unverified" in str(exc.value)
    assert not list((ws / "results").glob("promoted_*"))


def test_the_override_is_recorded_when_a_person_asked_for_it(tmp_path):
    ws = _ws(tmp_path)
    _gate(ws, "quantitative-validator", status="UNVERIFIED")

    assert router.promote(str(ws), STAMP, allow_unverified=True) is not None
    entry = json.loads((ws / "results" / router.PROMOTION_LOG)
                       .read_text(encoding="utf-8").strip())
    assert entry["approval"]["allow_unverified"] is True
    assert entry["approval"]["freshness"]["gates"] == 1


def test_the_override_cannot_be_added_after_the_token_was_issued(
        tmp_path, monkeypatch):
    """A strict approval is not spendable on a run that accepts UNVERIFIED."""
    monkeypatch.setattr(approval, "_human_channel",
                        lambda action="promote": True)
    ws = _ws(tmp_path)
    strict = approval.pipeline_params("a", "", [], None)
    lenient = approval.pipeline_params("a", "", [], None,
                                       allow_unverified=True)
    assert strict != lenient
    assert strict["allow_unverified"] is False

    approval.issue(str(ws), "promote", strict)
    with pytest.raises(approval.ApprovalRequired) as exc:
        approval.consume(str(ws), "promote", lenient)
    assert "different plan" in str(exc.value)


# -------------------------------------------------- atomic promotion

def test_a_crash_mid_copy_publishes_nothing(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    real_copytree = router.shutil.copytree

    def half_copy(src, dst, *a, **kw):
        real_copytree(src, dst, *a, **kw)
        (Path(dst) / "bands.csv").unlink()  # the copy stopped half-way
        raise OSError("disk full")

    monkeypatch.setattr(router.shutil, "copytree", half_copy)
    with pytest.raises(OSError):
        router.promote(str(ws), STAMP)

    assert not list((ws / "results").glob("promoted_*"))
    assert not (ws / "results" / router.PROMOTION_LOG).exists()


def test_a_leftover_staging_tree_is_cleaned_before_the_next_promotion(tmp_path):
    ws = _ws(tmp_path)
    leftover = ws / ".chelate" / "staging" / "promoted_OLD"
    leftover.mkdir(parents=True)
    (leftover / "half.txt").write_text("partial", encoding="utf-8")

    assert router.promote(str(ws), STAMP) is not None
    assert not leftover.exists()
    assert (ws / "results" / f"promoted_{STAMP}" / "bands.csv").is_file()
    # Nothing from staging leaked into the published set.
    published = ws / "results" / f"promoted_{STAMP}"
    assert not (published / "half.txt").exists()


def test_the_record_names_the_gates_the_promotion_rested_on(tmp_path):
    ws = _ws(tmp_path)
    rel = "material/initial/model.py"
    _gate(ws, "formula-validator",
          inputs={rel: _sha((ws / rel).read_text(encoding="utf-8"))})

    router.promote(str(ws), STAMP, {"source": "token", "nonce": "n1"})
    entry = json.loads((ws / "results" / router.PROMOTION_LOG)
                       .read_text(encoding="utf-8").strip())
    freshness = entry["approval"]["freshness"]
    assert freshness["bound"] == 1
    assert freshness["unbound"] == 0
    assert freshness["stale"] == []
    assert entry["files"][f"results/promoted_{STAMP}/bands.csv"]


# ------------------------------------------------- the scripted hatch

def test_the_scripted_hatch_is_named_as_what_it_is(monkeypatch):
    monkeypatch.delenv(approval.UNSAFE_AUTO_ENV, raising=False)
    monkeypatch.delenv("CHELATE_HUMAN", raising=False)
    monkeypatch.setattr(approval.sys.stdin, "isatty", lambda: False)

    assert approval._human_channel("promote") is False
    monkeypatch.setenv(approval.UNSAFE_AUTO_ENV, "1")
    assert approval._human_channel("promote") is True


def test_the_old_name_still_works_and_says_it_is_deprecated(
        monkeypatch, capsys):
    monkeypatch.delenv(approval.UNSAFE_AUTO_ENV, raising=False)
    monkeypatch.setenv("CHELATE_HUMAN", "1")

    assert approval._human_channel("promote") is True
    assert "pre-1.3.6 name" in capsys.readouterr().err


def test_no_environment_variable_means_no_channel(monkeypatch):
    monkeypatch.delenv(approval.UNSAFE_AUTO_ENV, raising=False)
    monkeypatch.delenv("CHELATE_HUMAN", raising=False)
    monkeypatch.setattr(approval.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "no")

    assert approval._human_channel("promote") is False


# ------------------------------------------------- provenance recording

def test_a_gate_written_by_the_adapter_binds_the_files_it_was_given(
        tmp_path, monkeypatch):
    """bootstrap.write_gate is the one choke point every skill writes through."""
    import bootstrap
    from contracts import pass_gate

    ws = _ws(tmp_path)
    model = ws / "material" / "initial" / "model.py"
    monkeypatch.setattr(bootstrap.sys, "argv",
                        ["skills/formula-validator/run.py",
                         "--root", str(ws), "--input", str(model)])
    gate = pass_gate("formula-validator", reason="checked")
    path = bootstrap.write_gate(str(ws), gate)

    written = json.loads(Path(path).read_text(encoding="utf-8"))
    assert written["inputs"]["material/initial/model.py"] == \
        _sha(model.read_text(encoding="utf-8"))
    assert written["provenance"]["gate_contract"] == 2
    assert written["provenance"]["skill_version"]
    assert written["provenance"]["skill_digest"]


def test_a_very_large_input_is_bound_by_size_not_by_digest(
        tmp_path, monkeypatch):
    """A multi-gigabyte video is not hashed on every gate write.

    The marker says so in the gate; freshness compares what was recorded, so
    a same-size edit is not detected — a limitation of the binding, not a
    silent claim that the bytes were digested.
    """
    import bootstrap

    ws = _ws(tmp_path)
    blob = ws / "material" / "initial" / "recording.bin"
    blob.write_bytes(b"0123456789")
    monkeypatch.setattr(bootstrap, "_LARGE_INPUT_BYTES", 4)

    inputs = bootstrap.declared_inputs(str(ws), ["--root", str(ws),
                                                "--input", str(blob)])
    assert inputs["material/initial/recording.bin"] == "large:10"

    _gate(ws, "video-tracker", inputs=inputs)
    assert router.stale_gates(str(ws)) == []
    blob.write_bytes(b"012345678X")          # same size: undetected
    assert router.stale_gates(str(ws)) == []
    blob.write_bytes(b"0123456789XYZ")       # new size: stale
    assert [s["skill"] for s in router.stale_gates(str(ws))] == ["video-tracker"]


def test_an_input_outside_the_workspace_is_bound_by_its_full_path(tmp_path):
    """Two `data.csv` from different folders must not collapse onto one key."""
    import bootstrap

    ws = _ws(tmp_path)
    outside = tmp_path / "elsewhere" / "data.csv"
    outside.parent.mkdir()
    outside.write_text("x,y\n1,2\n", encoding="utf-8")

    inputs = bootstrap.declared_inputs(
        str(ws), ["--root", str(ws), "--input", str(outside)])
    key = f"external:{outside.resolve()}"
    assert key in inputs

    _gate(ws, "data-profiler", inputs=inputs)
    assert router.stale_gates(str(ws)) == []
    outside.write_text("x,y\n1,3\n", encoding="utf-8")
    assert [s["skill"] for s in router.stale_gates(str(ws))] == ["data-profiler"]
