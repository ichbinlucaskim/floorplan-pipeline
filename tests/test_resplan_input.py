"""Real-ResPlan ingestion adapter + per-plan output + skip-with-warning (ADR-004).

The unit tests here are dataset-free (synthetic Shapely / wall dicts) so they run
in CI, where the 246 MB ResPlan.pkl is not checked out. The integration tests are
guarded by dataset availability and exercise the hero/crash plans end-to-end.
"""
import json

import pytest
from shapely.geometry import MultiPolygon, Polygon

from floorplan_pipeline import (
    load_resplan_plan,
    plan_id_str,
    record_to_rooms,
    run_pipeline_for_plan,
)
from floorplan_pipeline.resplan_input import _find_loader_dir, _record_id
from floorplan_pipeline.stages import stage_panels

# --- adapter unit tests (no dataset) ---------------------------------------

def test_plan_id_str_zero_pads():
    assert plan_id_str(8557) == "plan-008557"
    assert plan_id_str("8557") == "plan-008557"


def test_record_id_parses_both_forms():
    assert _record_id(8557) == 8557
    assert _record_id("plan-008557") == 8557


def test_record_to_rooms_explodes_multipolygon():
    """Each constituent polygon becomes one '{base}_{i}' room carrying its ring."""
    record = {
        "id": 1,
        "neighbor": [[0, 1]],            # non-geometry: skipped
        "living": Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]),
        "bedroom": MultiPolygon(
            [
                Polygon([(0, 0), (5, 0), (5, 5), (0, 5)]),
                Polygon([(5, 0), (9, 0), (9, 4), (5, 4)]),
            ]
        ),
        "door": Polygon().buffer(0),     # empty: skipped
    }
    rooms = record_to_rooms(record)
    ids = {r["id"] for r in rooms}
    assert ids == {"living_0", "bedroom_0", "bedroom_1"}
    for r in rooms:
        assert isinstance(r["points"], list) and len(r["points"]) >= 4


# --- skip-with-warning resilience (no dataset) -----------------------------

def _wall(wid, x1, y1, x2, y2, openings):
    return {
        "schema_version": "0.1.0", "id": wid,
        "start": {"x": x1, "y": y1}, "end": {"x": x2, "y": y2},
        "thickness": 171.0, "type": "interior", "load_bearing": False,
        "adjacent_rooms": ["a"], "hosted_openings": openings,
    }


def test_stage_panels_skips_unpanelizable_wall_and_continues():
    """An opening layout with no valid split is skipped (recorded), not fatal."""
    bad = _wall("w-bad", 0, 0, 8000, 0, ["op"])
    good = _wall("w-good", 0, 0, 2000, 0, [])
    openings = {
        "op": {
            "schema_version": "0.1.0", "id": "op", "host_wall": "w-bad",
            "opening_type": "door", "position": 1800.0, "width": 3600.0,
            "height": 2032.0, "sill_height": 0.0,
        }
    }
    skips: list[dict] = []
    with pytest.warns(UserWarning, match="skipping panels for w-bad"):
        panels, _ = stage_panels([bad, good], openings, skips=skips)

    assert [p["id"] for p in panels] == ["w-good-panel-000"]  # good wall survived
    assert len(skips) == 1
    assert skips[0]["stage"] == "panels"
    assert skips[0]["id"] == "w-bad"
    assert "MAX_PANEL_LENGTH_MM" in skips[0]["reason"]


# --- dataset-guarded integration tests -------------------------------------

def _dataset_available() -> bool:
    try:
        loader_dir = _find_loader_dir()
    except FileNotFoundError:
        return False
    return (loader_dir / "raw" / "ResPlan.pkl").exists()


needs_dataset = pytest.mark.skipif(
    not _dataset_available(), reason="ResPlan dataset not checked out"
)


@needs_dataset
def test_hero_plan_runs_clean_to_per_plan_folder(tmp_path):
    """plan-008557 runs end-to-end: per-plan folder, all artifacts, 0 skips."""
    summary = run_pipeline_for_plan("plan-008557", out_base=str(tmp_path))
    assert summary["plan_id"] == "plan-008557"
    assert summary["walls"] > 0 and summary["framing_members"] > 0
    assert summary["ifc_valid"] is True
    assert summary["skipped"] == 0

    plan_dir = tmp_path / "plan-008557"
    for name in (
        "walls.json", "panels.json", "openings.json", "framing.json", "bom.json",
        "member_sequences.json", "panel_sequence.json", "model.ifc", "summary.json",
    ):
        assert (plan_dir / name).exists(), f"missing {name}"
    # summary.json round-trips the returned summary.
    assert json.loads((plan_dir / "summary.json").read_text())["plan_id"] == "plan-008557"


@needs_dataset
def test_crash_plan_completes_with_skip_instead_of_crashing(tmp_path):
    """plan-016374 used to die on an uncaught panel ValueError; now it skips the
    bad unit, surfaces it in the summary, and still emits a valid IFC."""
    summary = run_pipeline_for_plan("plan-016374", out_base=str(tmp_path))
    assert summary["skipped"] >= 1
    assert summary["skipped_panels"] >= 1
    assert any(s["stage"] == "panels" for s in summary["skips"])
    assert summary["ifc_valid"] is True  # partial but valid


@needs_dataset
def test_load_resplan_plan_by_id_and_string_agree():
    pid_a, rooms_a = load_resplan_plan(8557)
    pid_b, rooms_b = load_resplan_plan("plan-008557")
    assert pid_a == pid_b == "plan-008557"
    assert len(rooms_a) == len(rooms_b) > 0
