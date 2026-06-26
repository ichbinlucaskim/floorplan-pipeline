import os


def test_ifc_validates(tmp_path, sample_rooms):
    """The end-to-end IFC must pass ifcopenshell.validate with 0 errors."""
    import ifcopenshell.validate

    from floorplan_pipeline import PipelineConfig, run_pipeline

    cfg = PipelineConfig(out_dir=str(tmp_path))
    run_pipeline(sample_rooms, cfg)

    path = os.path.join(str(tmp_path), "model.ifc")
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(path, logger)
    errors = [s for s in logger.statements if s.get("level") == "Error"]
    assert errors == [], f"IFC validation errors: {errors}"


def test_sequences_validate(tmp_path, sample_rooms):
    """Written member/panel sequences pass aec-schema validation."""
    import json

    from aec_schema import validate_sequence

    from floorplan_pipeline import PipelineConfig, run_pipeline

    run_pipeline(sample_rooms, PipelineConfig(out_dir=str(tmp_path)))
    panel_seq = json.loads((tmp_path / "panel_sequence.json").read_text())
    validate_sequence(panel_seq)
    for seq in json.loads((tmp_path / "member_sequences.json").read_text()).values():
        validate_sequence(seq)
