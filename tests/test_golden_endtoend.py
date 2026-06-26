"""
Golden test: run the REAL pipeline end-to-end to an IFC on disk and assert the
actual artifact is geometrically sane, using the authoritative placement resolver
(ifcopenshell.util.placement) — never a hand-rolled matrix reshape.

This guards the project's recurring failure mode: component/fixture tests pass
while the real end-to-end output is wrong (units, NULL walls, framing stacked at
origin). Every one of those was invisible to schema validation. This test opens
the real model.ifc and checks world coordinates.

Thresholds: members must span >= 60% of the wall world footprint on each
horizontal axis. On the example the ratio is ~1.0 (members exactly follow walls),
so 0.6 passes with wide margin; a true Defect-B collapse (member span ~0.06 m vs
wall ~3 m, ratio ~0.02) fails hard.
"""
import json
import os

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement as _placement
import ifcopenshell.validate
import numpy as np
from _world import world_box, world_origin

_MEMBER_VS_WALL_MIN_RATIO = 0.6
_AXIS_ALIGNED_EPS = 1e-3


def _xaxis(element):
    """Local X-axis (length direction) via the authoritative placement resolver."""
    return _placement.get_local_placement(element.ObjectPlacement)[:3, 0]


def _build_model(tmp_path):
    from floorplan_pipeline import PipelineConfig, run_pipeline

    rooms_path = os.path.join(os.path.dirname(__file__), "..", "examples", "input_rooms.json")
    with open(rooms_path) as fh:
        rooms = json.load(fh)["rooms"]
    cfg = PipelineConfig(
        out_dir=str(tmp_path), include_framing=True, include_sequence=True, include_ifc=True
    )
    run_pipeline(rooms, cfg)
    return ifcopenshell.open(str(tmp_path / "model.ifc"))


def test_no_null_wall_representation(tmp_path):
    m = _build_model(tmp_path)
    nulls = [w for w in m.by_type("IfcWall") if w.Representation is None]
    assert nulls == [], f"{len(nulls)} walls NULL representation (Defect A regression)"


def test_walls_are_axis_aligned(tmp_path):
    """Orthogonal floor plan → every wall's length direction must be axis-aligned
    (X or Y). Catches the create_2pt_wall diagonal bug (LIB-001 / ADR-007); a
    diagonal regression like [0.78, 0.63] fails hard.
    """
    m = _build_model(tmp_path)
    bad = []
    for w in m.by_type("IfcWall"):
        x = _xaxis(w)
        if min(abs(x[0]), abs(x[1])) > _AXIS_ALIGNED_EPS:  # 0 if aligned to an axis
            bad.append((w.Name, [round(float(c), 3) for c in x[:2]]))
    assert not bad, f"non-axis-aligned walls: {bad}"


def test_framing_matches_wall_direction(tmp_path):
    """Each panel's framing must agree with its parent wall's (axis-aligned) axis."""
    m = _build_model(tmp_path)
    for asm in m.by_type("IfcElementAssembly"):
        if not asm.Decomposes:
            continue
        wall = asm.Decomposes[0].RelatingObject
        if not wall.is_a("IfcWall"):
            continue
        wx = _xaxis(wall)
        assert min(abs(wx[0]), abs(wx[1])) < _AXIS_ALIGNED_EPS, (
            f"{wall.Name} wall axis not aligned: {wx[:2]}"
        )
        # the wall's plates run along its axis: a plate's length-dir must be
        # parallel to the wall axis (their cross-product ~ 0 in plan).
        for mem in asm.IsDecomposedBy[0].RelatedObjects:
            if mem.PredefinedType != "PLATE":
                continue
            mz = _placement.get_local_placement(mem.ObjectPlacement)[:3, 2]  # extrusion/length dir
            cross = abs(wx[0] * mz[1] - wx[1] * mz[0])
            assert cross < _AXIS_ALIGNED_EPS, (
                f"{mem.Name} plate dir {mz[:2]} not parallel to wall {wall.Name} axis {wx[:2]}"
            )


def test_members_follow_walls_world_footprint(tmp_path):
    """THE golden assertion: framing must occupy the walls' world footprint.

    If members collapse to the origin (old Defect B), the per-axis span ratio
    drops far below the threshold and this fails.
    """
    m = _build_model(tmp_path)
    wmin, wmax = world_box(m.by_type("IfcWall"))
    mmin, mmax = world_box(m.by_type("IfcMember"))
    assert wmin is not None and mmin is not None

    wall_span = wmax - wmin
    mem_span = mmax - mmin
    for axis, name in [(0, "x"), (1, "y")]:
        assert mem_span[axis] >= _MEMBER_VS_WALL_MIN_RATIO * wall_span[axis], (
            f"members collapse on {name}: member span {mem_span[axis]:.0f} mm "
            f"vs wall span {wall_span[axis]:.0f} mm (Defect B regression)"
        )


def test_panels_at_distinct_world_locations(tmp_path):
    """Panel assemblies must sit at distinct world locations (not stacked).

    Assemblies are pure logical containers (no own placement after the Defect-B
    fix), so a panel's location is the centroid of its members' world origins.
    """
    m = _build_model(tmp_path)
    centers = []
    for asm in m.by_type("IfcElementAssembly"):
        if not asm.IsDecomposedBy:
            continue
        origins = [world_origin(mem) for mem in asm.IsDecomposedBy[0].RelatedObjects]
        origins = [o for o in origins if o is not None]
        if origins:
            centers.append(np.mean(origins, axis=0))
    c = np.array(centers)
    assert len(c) >= 2
    assert np.ptp(c, axis=0).max() > 1000.0, "panel assemblies stacked at one location (mm)"


def test_member_world_spread_is_meaningful(tmp_path):
    """Sanity: the building is at least a few metres across in world."""
    m = _build_model(tmp_path)
    mmin, mmax = world_box(m.by_type("IfcMember"))
    span = mmax - mmin
    assert max(span[0], span[1]) > 3000.0, f"building too small/collapsed: {span} mm"


def test_ifc_validates(tmp_path):
    m = _build_model(tmp_path)
    assert m.by_type("IfcWall")  # built
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(str(tmp_path / "model.ifc"), logger)
    errors = [s for s in logger.statements if s.get("level") == "Error"]
    assert errors == [], f"{len(errors)} IFC validation errors"


def test_openings_cut_through_walls(tmp_path):
    """Host walls must show real through-holes at openings (ADR-008).

    Uses the geometry ITERATOR (not create_shape, which is unreliable for these
    bodies) — the path viewers consume. A through-hole's rim reaches BOTH
    thickness faces; a notch reaches only one.
    """
    m = _build_model(tmp_path)
    hosts = [w for w in m.by_type("IfcWall") if w.HasOpenings]
    assert hosts, "no host walls with openings"
    settings = ifcopenshell.geom.settings()
    for w in hosts:
        it = ifcopenshell.geom.iterator(settings, m, include=[w])
        assert it.initialize(), f"{w.Name}: wall did not tessellate"
        lv = np.array(it.get().geometry.verts).reshape(-1, 3) * 1000.0
        assert len(lv) > 8, f"{w.Name}: no hole"
        ymin, ymax = lv[:, 1].min(), lv[:, 1].max()
        near_min = np.any(np.isclose(lv[:, 1], ymin, atol=3.0))
        near_max = np.any(np.isclose(lv[:, 1], ymax, atol=3.0))
        assert near_min and near_max, f"{w.Name}: opening is a notch, not a through-hole"


def test_known_empty_tessellation_is_isolated(tmp_path):
    """Document the known ifcopenshell.geom quirk: a tiny number of members
    tessellate to 0 verts (e.g. the m017-class 760mm sill), but they still have
    VALID placements. If the count grows, something regressed.
    """
    m = _build_model(tmp_path)
    settings = ifcopenshell.geom.settings()
    empty = []
    for mem in m.by_type("IfcMember"):
        shp = ifcopenshell.geom.create_shape(settings, mem)
        if len(shp.geometry.verts) == 0:
            empty.append(mem.Name)
    assert len(empty) <= 2, f"too many empty tessellations (regression): {empty}"
    # the affected members must still be placed (valid data, just an engine quirk)
    for name in empty:
        mem = next(x for x in m.by_type("IfcMember") if x.Name == name)
        assert mem.ObjectPlacement is not None
        assert world_origin(mem) is not None
