"""
End-to-end orchestration: rooms -> walls -> panels -> framing -> {sequence, IFC}.

Each seam is schema-validated before the next stage consumes it (ADR-002): a
contract break fails loud, which is the whole point of an integration repo.
"""
from __future__ import annotations

import json
from pathlib import Path

from aec_schema import (
    validate_bom,
    validate_framing,
    validate_panel,
    validate_sequence,
    validate_wall,
)

from .config import PipelineConfig
from .stages import stage_framing, stage_ifc, stage_panels, stage_sequences, stage_walls


def _write(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2))


def _ifc_is_valid(path: Path) -> bool:
    import ifcopenshell.validate

    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(str(path), logger)
    return not [s for s in logger.statements if s.get("level") == "Error"]


def run_pipeline(
    rooms: list[dict],
    config: PipelineConfig | None = None,
    *,
    plan_id: str = "pipeline-000",
) -> dict:
    """Run the full pipeline end-to-end, writing artifacts to ``config.out_dir``.

    ``plan_id`` flows into the generated wall/panel ids and the summary; callers
    running a real ResPlan plan pass e.g. ``"plan-008557"`` (see
    :func:`floorplan_pipeline.run_pipeline_for_plan`). Returns a summary dict of
    per-stage counts, skips, and artifact paths — also written to
    ``summary.json``.
    """
    config = config or PipelineConfig()
    out = Path(config.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Domain-limit skips (out-of-envelope panels/framing) are surfaced here, not
    # silently dropped — counted and reported in the summary (ADR-004).
    skips: list[dict] = []

    # --- walls ---
    walls, openings = stage_walls(rooms, plan_id=plan_id)
    for wall in walls:
        validate_wall(wall)
    _write(out / "walls.json", walls)
    _write(out / "openings.json", openings)

    # --- panels ---
    panels, panel_openings = stage_panels(
        walls, openings, height_mm=config.wall_height_mm, skips=skips
    )
    for panel in panels:
        validate_panel(panel)
    _write(out / "panels.json", panels)

    summary: dict = {
        "plan_id": plan_id,
        "rooms": len(rooms),
        "walls": len(walls),
        "panels": len(panels),
        "openings": len(openings),
    }

    # --- framing ---
    framings: dict[str, dict] = {}
    if config.include_framing:
        framings, boms = stage_framing(panels, panel_openings, skips=skips)
        for framing in framings.values():
            validate_framing(framing)
        for bom in boms.values():
            validate_bom(bom)
        _write(out / "framing.json", list(framings.values()))
        _write(out / "bom.json", list(boms.values()))
        summary["framing_panels"] = len(framings)
        summary["framing_members"] = sum(f["member_count"] for f in framings.values())

    # --- sequences ---
    if config.include_sequence and framings:
        member_sequences, panel_sequence = stage_sequences(framings, panels)
        for seq in member_sequences.values():
            validate_sequence(seq)
        validate_sequence(panel_sequence)
        _write(out / "member_sequences.json", member_sequences)
        _write(out / "panel_sequence.json", panel_sequence)
        summary["member_sequences"] = len(member_sequences)
        summary["panel_steps"] = len(panel_sequence["steps"])

    # --- IFC ---
    if config.include_ifc:
        ifc_path = out / "model.ifc"
        framing_arg = framings if config.include_framing else {}
        stage_ifc(walls, openings, framing_arg, panels, str(ifc_path), config.wall_height_mm)
        summary["ifc_path"] = str(ifc_path)
        summary["ifc_valid"] = _ifc_is_valid(ifc_path)

    # --- skips (panels + framing, accounted not dropped) ---
    summary["skipped"] = len(skips)
    summary["skipped_panels"] = sum(1 for s in skips if s["stage"] == "panels")
    summary["skipped_framing"] = sum(1 for s in skips if s["stage"] == "framing")
    summary["skips"] = skips

    _write(out / "summary.json", summary)
    return summary
