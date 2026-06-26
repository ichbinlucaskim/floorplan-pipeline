"""Each seam must hand a schema-valid artifact to the next stage."""
from aec_schema import validate_framing, validate_panel, validate_wall

from floorplan_pipeline.stages import stage_framing, stage_panels, stage_walls


def test_walls_pass_schema(sample_rooms):
    walls, _ = stage_walls(sample_rooms)
    assert walls
    for w in walls:
        validate_wall(w)


def test_panels_pass_schema(sample_rooms):
    walls, op = stage_walls(sample_rooms)
    panels, _ = stage_panels(walls, op)
    assert panels
    for p in panels:
        validate_panel(p)


def test_framing_pass_schema(sample_rooms):
    walls, op = stage_walls(sample_rooms)
    panels, pop = stage_panels(walls, op)
    framings, _ = stage_framing(panels, pop)
    assert framings
    for f in framings.values():
        validate_framing(f)


def test_openings_propagate_panel_local(sample_rooms):
    """The opening map must survive the wall->panel seam (panel-local positions)."""
    walls, op = stage_walls(sample_rooms)
    panels, pop = stage_panels(walls, op)
    assert pop, "openings lost across the panel seam"
    assert set(pop) <= set(op)  # same opening ids, panel-local geometry
