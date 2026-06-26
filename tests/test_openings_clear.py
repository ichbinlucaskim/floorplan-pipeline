"""Regression: every opening must render as a clear passage (ADR-006).

Before the partition-wall merge, ResPlan's double-walled partitions left a solid
twin wall behind each interior door, so doors rendered blocked (filled with the
twin wall + its studs) while windows on single exterior walls were clear. This
test opens the REAL hero IFC and asserts no opening's clear volume is occupied by
a foreign wall body or full-height member.

Measurement is via the geometry ITERATOR + world coordinates (exact for this
orthogonal, axis-aligned model) — never create_shape, never a raw matrix reshape
(the project's documented failure modes). The clear volume is
``[opening span shrunk 40mm] x [host wall thickness band] x [z 1000-1800mm]`` — a
z-band open for both doors (0-2032) and window glazing (900-2100). The host wall
body and its OWN framing are excluded; a corner-adjacent perpendicular wall only
clips a sliver (<=~10% of the span) and is not counted.

Dataset-guarded: skips when ResPlan.pkl is not checked out (e.g. CI).
"""
import numpy as np
import pytest

from floorplan_pipeline import run_pipeline_for_plan
from floorplan_pipeline.resplan_input import _find_loader_dir


def _dataset_available() -> bool:
    try:
        return (_find_loader_dir() / "raw" / "ResPlan.pkl").exists()
    except FileNotFoundError:
        return False


needs_dataset = pytest.mark.skipif(
    not _dataset_available(), reason="ResPlan dataset not checked out"
)


def _blocked_openings(ifc_path: str) -> list[str]:
    """Return the names of openings whose clear volume is obstructed."""
    import ifcopenshell
    import ifcopenshell.geom

    m = ifcopenshell.open(ifc_path)
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    it = ifcopenshell.geom.iterator(settings, m)
    aabb: dict[str, tuple] = {}
    kind: dict[str, str] = {}
    if it.initialize():
        while True:
            sh = it.get()
            v = np.array(sh.geometry.verts).reshape(-1, 3) * 1000.0
            if len(v):
                aabb[sh.guid] = (v.min(0), v.max(0))
                kind[sh.guid] = m.by_guid(sh.guid).is_a()
            if not it.next():
                break

    member_host: dict[str, str] = {}
    for asm in m.by_type("IfcElementAssembly"):
        if not asm.Decomposes:
            continue
        hw = asm.Decomposes[0].RelatingObject
        for mem in (asm.IsDecomposedBy[0].RelatedObjects if asm.IsDecomposedBy else []):
            member_host[mem.GlobalId] = hw.GlobalId

    blocked = []
    for w in m.by_type("IfcWall"):
        if not w.HasOpenings:
            continue
        wmn, wmx = aabb[w.GlobalId]
        ext = wmx - wmn
        ta = 0 if ext[0] < ext[1] else 1  # thickness axis
        sa = 1 - ta                       # span axis
        for rel in w.HasOpenings:
            op = rel.RelatedOpeningElement
            if op.GlobalId not in aabb:
                continue
            omn, omx = aabb[op.GlobalId]
            width = omx[sa] - omn[sa]
            blo, bhi = omn[sa] + 40.0, omx[sa] - 40.0
            box_lo = np.array([-1e9, -1e9, 1000.0])
            box_hi = np.array([1e9, 1e9, 1800.0])
            box_lo[sa], box_hi[sa] = blo, bhi
            box_lo[ta], box_hi[ta] = wmn[ta], wmx[ta]
            for g, (mn, mx) in aabb.items():
                if g == w.GlobalId or kind[g] == "IfcOpeningElement":
                    continue
                if member_host.get(g) == w.GlobalId:
                    continue
                if not all(min(box_hi[i], mx[i]) - max(box_lo[i], mn[i]) > 1.0 for i in range(3)):
                    continue
                span_ov = min(bhi, mx[sa]) - max(blo, mn[sa])
                if kind[g] == "IfcWall" and span_ov > 0.5 * width:
                    blocked.append(op.Name)
                    break
                centre = 0.5 * (mn[sa] + mx[sa])
                full_height = mn[2] < 1000 and mx[2] > 1800
                if kind[g] == "IfcMember" and full_height and blo < centre < bhi:
                    blocked.append(op.Name)
                    break
    return blocked


@needs_dataset
def test_hero_openings_render_clear(tmp_path):
    """plan-008557: with the partition merge, no door or window is blocked by a
    foreign wall/member (was 6 doors blocked before the merge)."""
    summary = run_pipeline_for_plan("plan-008557", out_base=str(tmp_path))
    ifc_path = summary["ifc_path"]
    blocked = _blocked_openings(ifc_path)
    assert blocked == [], f"openings blocked by a foreign wall/member: {blocked}"
