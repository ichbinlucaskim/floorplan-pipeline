"""
Authoritative world-placement helpers for tests.

World-coordinate assertions MUST go through ifcopenshell.util.placement, which
resolves the full IfcLocalPlacement chain to a 4x4 matrix (translation in column
3). Do NOT hand-roll `np.array(shape.transformation.matrix).reshape(4,4)[:3,3]`
— that read is column-major and misreads the translation, which produced a false
"framing collapsed" alarm (see aec-ifc-export DEFECT_B_DIAGNOSIS.md / ADR-006).
"""
from __future__ import annotations

import ifcopenshell.util.placement
import numpy as np


def world_origin(element) -> np.ndarray | None:
    """World translation of an element via the authoritative placement resolver."""
    if element.ObjectPlacement is None:
        return None
    return ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)[:3, 3]


def world_box(elements) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Axis-aligned world bounding box (min, max) over element origins.

    Skips elements without placement (and any NaN). Returns (None, None) if empty.
    """
    pts = [world_origin(e) for e in elements]
    pts = [p for p in pts if p is not None and not np.isnan(p).any()]
    if not pts:
        return None, None
    a = np.array(pts)
    return a.min(0), a.max(0)
