"""Content-addressed input snapshots: the check and the use read the same bytes.

The gate records a digest and promotion re-checks it, which catches a file
edited between the check and the delivery. It does not catch an edit between
the check and the skill's own ``open()`` — that is the window these tests
close: the run reads a frozen copy, and the gate points back at the original
through the snapshot's manifest.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import router, snapshot


def _ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / "material" / "initial").mkdir(parents=True)
    (ws / "process" / "gates").mkdir(parents=True)
    return ws


def test_a_snapshot_is_addressed_by_content_and_reused(tmp_path):
    ws = _ws(tmp_path)
    model = ws / "material" / "initial" / "model.py"
    model.write_text("H = 1\n", encoding="utf-8")

    first = snapshot.materialise(str(ws), [str(model)])
    second = snapshot.materialise(str(ws), [str(model)])
    assert first["id"] == second["id"]
    assert first["files"] == second["files"]
    assert len(list((ws / ".chelate" / "snapshots").iterdir())) == 1


def test_editing_the_original_does_not_change_the_frozen_copy(tmp_path):
    """The window this exists for: change the file while the run is in flight."""
    ws = _ws(tmp_path)
    model = ws / "material" / "initial" / "model.py"
    model.write_text("H = 1  # checked\n", encoding="utf-8")

    frozen = snapshot.materialise(str(ws), [str(model)])
    snap_path = Path(frozen["files"][str(model.resolve())])
    before = snap_path.read_bytes()

    model.write_text("H = 0  # swapped mid-run\n", encoding="utf-8")

    assert snap_path.read_bytes() == before
    assert "checked" in before.decode("utf-8")


def test_the_manifest_maps_a_snapshot_file_back_to_its_original(tmp_path):
    ws = _ws(tmp_path)
    model = ws / "material" / "initial" / "model.py"
    model.write_text("H = 1\n", encoding="utf-8")
    frozen = snapshot.materialise(str(ws), [str(model)])

    rel = f"{frozen['dir']}/files/model.py"
    origin = snapshot.origin_of(str(ws), rel)
    assert origin["original"] == "material/initial/model.py"
    import hashlib
    assert origin["sha256"] == hashlib.sha256(
        model.read_bytes()).hexdigest()
    # A path outside a snapshot is left to the caller's ordinary handling.
    assert snapshot.origin_of(str(ws), "material/initial/model.py") is None


def test_a_gate_over_a_snapshot_expires_when_the_original_changes(tmp_path):
    """Freshness follows the manifest, so the user's file is what is checked."""
    ws = _ws(tmp_path)
    model = ws / "material" / "initial" / "model.py"
    model.write_text("H = 1\n", encoding="utf-8")
    frozen = snapshot.materialise(str(ws), [str(model)])
    rel = f"{frozen['dir']}/files/model.py"
    digest = snapshot.origin_of(str(ws), rel)["sha256"]

    gate = {"skill": "formula-validator", "status": "PASS",
            "evidence_level": "EXACT", "reason": "checked the snapshot",
            "timestamp": "2026-01-01T00:00:00Z",
            "inputs": {rel: digest}}
    (ws / "process" / "gates" / "formula-validator_20260101T000000Z.json") \
        .write_text(json.dumps(gate), encoding="utf-8")

    assert router.stale_gates(str(ws)) == []

    model.write_text("H = 0\n", encoding="utf-8")
    stale = router.stale_gates(str(ws))
    assert [s["skill"] for s in stale] == ["formula-validator"]
    # The mismatch names the user's file, not the internal snapshot copy.
    assert "material/initial/model.py" in stale[0]["reason"]


def test_the_snapshot_itself_is_what_the_adapter_is_handed(tmp_path,
                                                           monkeypatch):
    """A run wires the frozen path; the original is reported alongside it."""

    ws = _ws(tmp_path)
    csv = ws / "material" / "initial" / "data.csv"
    csv.write_text("x,y\n1,2\n", encoding="utf-8")

    seen = {}

    def fake_run_skill(rec, root, action, extra, timeout=600, debug=False):
        seen[rec.name] = list(extra)
        return {"skill": rec.name, "stage": rec.stage, "action": action,
                "status": "PASS", "evidence_level": "EXACT", "reason": "stub",
                "artifacts": [], "seconds": 0.0}

    monkeypatch.setattr(router, "run_skill", fake_run_skill)
    monkeypatch.setattr(router, "_adapter_accepts_input",
                        lambda rec, cache=None: True)
    result = router.run(str(ws), mode="c", selected=["data-profiler"],
                        inputs=[str(csv)], dry_run=False,
                        require_approval=False)

    wired = result["auto_inputs"]["data-profiler"]
    assert "snapshots" in wired
    assert seen["data-profiler"] == ["--input", wired]
    assert result["snapshot"]["files"]["material/initial/data.csv"] == \
        Path(wired).relative_to(ws).as_posix()


def test_an_input_too_large_to_freeze_is_dispatched_from_the_original(
        tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    blob = ws / "material" / "initial" / "recording.mp4"
    blob.write_bytes(b"x" * 64)
    monkeypatch.setattr(snapshot, "MAX_SNAPSHOT_BYTES", 8)

    frozen = snapshot.materialise(str(ws), [str(blob)])
    assert frozen["id"] == ""
    assert frozen["skipped"] == [str(blob.resolve())]


def test_pruning_keeps_the_newest_snapshots(tmp_path):
    ws = _ws(tmp_path)
    for i in range(4):
        f = ws / "material" / "initial" / f"v{i}.txt"
        f.write_text(f"{i}\n", encoding="utf-8")
        snapshot.materialise(str(ws), [str(f)])

    assert snapshot.prune(str(ws), keep=2) == 2
    assert len(list((ws / ".chelate" / "snapshots").iterdir())) == 2


def test_pruning_protects_a_snapshot_a_gate_still_names(tmp_path):
    """Deleting it would turn a current PASS into "input missing"."""
    import json as _json

    ws = _ws(tmp_path)
    model = ws / "material" / "initial" / "model.py"
    model.write_text("H = 1\n", encoding="utf-8")
    frozen = snapshot.materialise(str(ws), [str(model)])
    rel = f"{frozen['dir']}/files/model.py"
    (ws / "process" / "gates" / "formula-validator_20260101T000000Z.json") \
        .write_text(_json.dumps({
            "skill": "formula-validator", "status": "PASS",
            "timestamp": "2026-01-01T00:00:00Z",
            "inputs": {rel: snapshot.origin_of(str(ws), rel)["sha256"]},
        }), encoding="utf-8")

    assert frozen["id"] in snapshot.referenced(str(ws))
    # keep=0 would delete everything unmanaged; the gate's id survives.
    assert snapshot.prune(str(ws), keep=0, protect=snapshot.referenced(str(ws))) == 0
    assert (ws / ".chelate" / "snapshots" / frozen["id"]).is_dir()


def test_pruning_removes_old_data_copies_nothing_references(tmp_path):
    """A workspace must not accumulate a shadow archive of everything read."""
    ws = _ws(tmp_path)
    first = ws / "material" / "initial" / "old.txt"
    first.write_text("old data\n", encoding="utf-8")
    old = snapshot.materialise(str(ws), [str(first)])

    for i in range(3):
        f = ws / "material" / "initial" / f"new{i}.txt"
        f.write_text(f"{i}\n", encoding="utf-8")
        snapshot.materialise(str(ws), [str(f)])

    assert snapshot.prune(str(ws), keep=2, protect=snapshot.referenced(str(ws))) == 2
    assert not (ws / ".chelate" / "snapshots" / old["id"]).exists()


def test_a_file_wired_by_skill_arg_is_frozen_too(tmp_path, monkeypatch):
    """`--skill-arg x:--input f` must not be the hole beside the snapshot."""
    ws = _ws(tmp_path)
    draft = ws / "material" / "initial" / "draft.md"
    draft.write_text("# draft\n", encoding="utf-8")

    seen = {}

    def fake_run_skill(rec, root, action, extra, timeout=600, debug=False):
        seen[rec.name] = list(extra)
        return {"skill": rec.name, "stage": rec.stage, "action": action,
                "status": "PASS", "evidence_level": "EXACT", "reason": "stub",
                "artifacts": [], "seconds": 0.0}

    monkeypatch.setattr(router, "run_skill", fake_run_skill)
    router.run(str(ws), mode="c", selected=["data-profiler"],
               skill_args={"data-profiler": ["--input", str(draft)]},
               dry_run=False, require_approval=False)

    wired = seen["data-profiler"]
    assert wired[0] == "--input"
    assert "snapshots" in wired[1]
    assert Path(wired[1]).name == "draft.md"
