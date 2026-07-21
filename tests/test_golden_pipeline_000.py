"""
Golden byte-stable lock of the synthetic ``pipeline-000`` run.

Existing tests assert IFC *geometry* (world placement, validity). They do NOT
notice if a refactor silently changes the JSON artifacts the pipeline emits --
which is exactly the data a downstream persistence/service layer will project
into a database. This test closes that gap: it runs the real pipeline for the
committed synthetic plan and asserts the emitted artifacts are byte-identical to
committed golden fixtures.

Reproducible from the repo alone: the input is ``examples/input_rooms.json``
(committed), so no uncommitted ResPlan dataset is required.

Normalization (see docs/decisions.md, ADR on the golden lock):
* ``summary.json`` -- only the ``ifc_path`` VALUE is normalized to ``<IFC_PATH>``
  because it embeds the absolute output directory, which is environment- and
  run-dependent. Every other byte of the summary is locked.
* ``model.ifc`` -- NOT byte-locked. IfcOpenShell emits a wall-clock header
  timestamp, a random GlobalId per entity, nondeterministic set ordering, and
  nondeterministic instance-id (#N) numbering; none are values the pipeline
  controls or that should be stable. It is locked instead by a canonical
  structural signature (IFC schema, validation error count, per-entity-type
  counts), which is deterministic across runs. IFC geometry remains covered by
  ``test_golden_endtoend.py`` and ``test_artifacts_valid.py``.
"""
import json
import re
from collections import Counter
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate

from floorplan_pipeline import PipelineConfig, run_pipeline

GOLDEN = Path(__file__).parent / "golden" / "pipeline-000"
INPUT = Path(__file__).parent.parent / "examples" / "input_rooms.json"

# Artifacts that are already byte-deterministic run-to-run.
BYTE_STABLE = [
    "walls.json",
    "openings.json",
    "panels.json",
    "framing.json",
    "bom.json",
    "member_sequences.json",
    "panel_sequence.json",
]


def _normalize_summary(text: str) -> str:
    """Blank only the environment-dependent absolute ``ifc_path`` value."""
    return re.sub(r'("ifc_path": ")[^"]*(")', r"\1<IFC_PATH>\2", text)


def _ifc_signature(path: Path) -> dict:
    model = ifcopenshell.open(str(path))
    log = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(str(path), log)
    errors = sum(1 for s in log.statements if s.get("level") == "Error")
    return {
        "schema": model.schema,
        "error_count": errors,
        "entity_counts": dict(sorted(Counter(e.is_a() for e in model).items())),
    }


def _run(out_dir: Path) -> None:
    rooms = json.loads(INPUT.read_text())["rooms"]
    run_pipeline(rooms, PipelineConfig(out_dir=str(out_dir)), plan_id="pipeline-000")


def test_json_artifacts_are_byte_identical_to_golden(tmp_path):
    _run(tmp_path)
    mismatches = []
    for name in BYTE_STABLE:
        produced = (tmp_path / name).read_bytes()
        expected = (GOLDEN / name).read_bytes()
        if produced != expected:
            mismatches.append(name)
    assert not mismatches, f"artifacts drifted from golden (byte-level): {mismatches}"


def test_summary_is_byte_identical_after_ifc_path_normalization(tmp_path):
    _run(tmp_path)
    produced = _normalize_summary((tmp_path / "summary.json").read_text())
    expected = (GOLDEN / "summary.json").read_text()
    assert produced == expected


def test_ifc_structural_signature_matches_golden(tmp_path):
    _run(tmp_path)
    produced = _ifc_signature(tmp_path / "model.ifc")
    expected = json.loads((GOLDEN / "ifc_signature.json").read_text())
    assert produced == expected
