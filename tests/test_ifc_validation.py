"""
Tests for the IFC validation-statement surfacing path (validate_ifc).

``validate_ifc`` returns both the boolean verdict and the raw ifcopenshell
validation statements, so a downstream persistence layer can record failures
without a second validation code path. ``_ifc_is_valid`` stays a plain-bool
wrapper for the existing pipeline summary caller.
"""
import json
from pathlib import Path

from floorplan_pipeline import IfcValidation, PipelineConfig, run_pipeline, validate_ifc
from floorplan_pipeline.pipeline import _ifc_is_valid

INPUT = Path(__file__).parent.parent / "examples" / "input_rooms.json"

# A deliberately invalid IFC4: '.BOGUSVALUE.' is not a member of IfcWallTypeEnum,
# so ifcopenshell.validate emits one error-level statement.
_INVALID_IFC = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''),'2;1');
FILE_NAME('','2020-01-01T00:00:00',(''),(''),'test','test','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCWALL('0000000000000000000002',$,'w',$,$,$,$,$,.BOGUSVALUE.);
ENDSEC;
END-ISO-10303-21;
"""


def _valid_ifc(out_dir: Path) -> Path:
    """Produce a known-valid IFC by running the real pipeline for pipeline-000."""
    rooms = json.loads(INPUT.read_text())["rooms"]
    run_pipeline(rooms, PipelineConfig(out_dir=str(out_dir)), plan_id="pipeline-000")
    return out_dir / "model.ifc"


def test_validate_ifc_valid_case_returns_no_statements(tmp_path):
    result = validate_ifc(_valid_ifc(tmp_path))
    assert isinstance(result, IfcValidation)
    assert result.is_valid is True
    assert result.statements == ()


def test_validate_ifc_invalid_case_surfaces_statements(tmp_path):
    bad = tmp_path / "bad.ifc"
    bad.write_text(_INVALID_IFC)

    result = validate_ifc(bad)

    assert result.is_valid is False
    assert len(result.statements) >= 1
    # The statements carry the shape the validation_errors table will store.
    stmt = result.statements[0]
    assert stmt.get("level") == "error"
    assert "message" in stmt
    assert "instance" in stmt


def test_ifc_is_valid_wrapper_stays_a_plain_bool(tmp_path):
    valid = _valid_ifc(tmp_path)
    bad = tmp_path / "bad.ifc"
    bad.write_text(_INVALID_IFC)

    # Identity checks: the wrapper must return genuine bools, not truthy objects,
    # because existing callers assert ``summary["ifc_valid"] is True``.
    assert _ifc_is_valid(valid) is True
    assert _ifc_is_valid(bad) is False
