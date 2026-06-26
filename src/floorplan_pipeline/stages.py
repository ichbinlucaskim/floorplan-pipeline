"""
Thin wrappers over each component repo.

Each stage takes the prior stage's output (aec-schema-conforming dicts) and
returns the next. There is NO domain logic here — only calls into the component
packages and data pass-through. If a change here starts to look like extraction /
framing / sequencing logic, it belongs in the component repo, not this file.
"""
from __future__ import annotations

import warnings
from typing import Any

from aec_ifc_export import export_ifc
from assembly_sequence import sequence_members, sequence_panels
from framing_synth import compute_bom, synthesize_framing
from panel_decompose import decompose_walls
from shapely.geometry import Polygon
from wall_extract import extract_walls


def _rooms_to_record(rooms: list[dict]) -> dict[str, Polygon]:
    """{'id','points'} dicts -> {id: Shapely Polygon} record for wall-extract.

    Points are ResPlan pixel coordinates (wall-extract scales by PX_TO_MM). The
    id base (e.g. 'living', 'door') is what wall-extract classifies on.
    """
    return {r["id"]: Polygon(r["points"]) for r in rooms}


def stage_walls(rooms: list[dict], *, plan_id: str = "pipeline-000") -> tuple[list[dict], dict]:
    """rooms -> (walls, wall-relative opening geometry map)."""
    record = _rooms_to_record(rooms)
    walls, openings = extract_walls(record, plan_id=plan_id, return_openings=True)
    return walls, openings


def stage_panels(
    walls: list[dict],
    openings: dict,
    *,
    height_mm: float = 2438.0,
    skips: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    """walls -> (panels, panel-local opening geometry map).

    A wall whose opening layout leaves no split keeping every panel under
    ``MAX_PANEL_LENGTH_MM`` raises ValueError in panel-decompose; that is a
    documented domain limit (not a seam break), so the wall is skipped with a
    warning and the run continues — mirroring :func:`stage_framing` (ADR-004,
    option B). Decomposing per-wall is output-identical to one bulk call:
    panel-decompose already processes walls independently and namespaces panel
    ids by ``wall['id']``, so there is no cross-wall coupling to lose.

    Skipped walls are appended to ``skips`` (if provided) as
    ``{"stage", "id", "reason"}`` dicts so the pipeline can report them.
    """
    panels: list[dict] = []
    panel_openings: dict = {}
    for wall in walls:
        try:
            wall_panels, wall_openings = decompose_walls(
                [wall], openings=openings, height_mm=height_mm, return_openings=True
            )
        except ValueError as exc:
            warnings.warn(f"skipping panels for {wall['id']}: {exc}", stacklevel=2)
            if skips is not None:
                skips.append({"stage": "panels", "id": wall["id"], "reason": str(exc)})
            continue
        panels.extend(wall_panels)
        panel_openings.update(wall_openings)
    return panels, panel_openings


def stage_framing(
    panels: list[dict],
    openings: dict,
    *,
    skips: list[dict] | None = None,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """each panel -> framing dict + BOM, keyed by panel id.

    A panel whose opening is outside framing-synth's prescriptive envelope raises
    ValueError; that is a documented domain limit (not a seam break), so it is
    skipped with a warning — mirroring framing-synth's own demo. Skipped panels
    are appended to ``skips`` (if provided), matching :func:`stage_panels`.
    """
    framings: dict[str, dict] = {}
    boms: dict[str, dict] = {}
    for panel in panels:
        try:
            framing = synthesize_framing(panel, openings=openings or None)
        except ValueError as exc:
            warnings.warn(f"skipping framing for {panel['id']}: {exc}", stacklevel=2)
            if skips is not None:
                skips.append({"stage": "framing", "id": panel["id"], "reason": str(exc)})
            continue
        framings[panel["id"]] = framing
        boms[panel["id"]] = compute_bom(framing, panel)
    return framings, boms


def stage_sequences(
    framings: dict[str, dict],
    panels: list[dict],
) -> tuple[dict[str, dict], dict]:
    """framings -> per-panel member sequences; panels -> one panel sequence."""
    member_sequences = {pid: sequence_members(fr) for pid, fr in framings.items()}
    panel_sequence = sequence_panels(panels)
    return member_sequences, panel_sequence


def stage_ifc(
    walls: list[dict],
    openings: dict,
    framings: dict[str, dict],
    panels: list[dict],
    out_path: str,
    wall_height_mm: float,
) -> Any:
    """all artifacts -> IFC4 file. Openings void into walls (wall-relative)."""
    panels_map = {p["id"]: p for p in panels}
    framing_list = list(framings.values()) if framings else None
    return export_ifc(
        walls,
        openings=openings,
        framing=framing_list,
        panels=panels_map,
        wall_height_mm=wall_height_mm,
        out_path=out_path,
    )
