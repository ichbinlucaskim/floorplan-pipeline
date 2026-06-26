import os

from floorplan_pipeline import PipelineConfig, run_pipeline


def test_full_run_produces_all_artifacts(tmp_path, sample_rooms):
    cfg = PipelineConfig(
        out_dir=str(tmp_path),
        include_framing=True,
        include_sequence=True,
        include_ifc=True,
    )
    summary = run_pipeline(sample_rooms, cfg)
    assert summary["walls"] > 0
    assert summary["panels"] >= summary["walls"]  # long walls split into >= 1 panel each
    assert summary["framing_members"] > 0
    assert summary["ifc_valid"] is True

    for f in [
        "walls.json", "panels.json", "framing.json", "panel_sequence.json", "model.ifc"
    ]:
        assert os.path.exists(os.path.join(str(tmp_path), f))


def test_walls_only_mode(tmp_path, sample_rooms):
    """framing off -> still produces a valid walls-only IFC (the 'common cut')."""
    cfg = PipelineConfig(
        out_dir=str(tmp_path), include_framing=False, include_sequence=False
    )
    summary = run_pipeline(sample_rooms, cfg)
    assert summary["walls"] > 0
    assert summary.get("framing_members", 0) == 0
    assert summary["ifc_valid"] is True


def test_summary_counts_consistent(tmp_path, sample_rooms):
    summary = run_pipeline(sample_rooms, PipelineConfig(out_dir=str(tmp_path)))
    assert summary["member_sequences"] == summary["framing_panels"]
    assert summary["panel_steps"] == summary["panels"]
