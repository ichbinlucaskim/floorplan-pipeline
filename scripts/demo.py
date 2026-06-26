"""
Full end-to-end run: rooms -> walls -> panels -> framing -> {sequence, IFC}.

Two modes:

* No argument — runs the synthetic ``examples/input_rooms.json`` (plan id
  ``pipeline-000``), landing in ``out/pipeline-000/``.
* A plan id argument (e.g. ``python scripts/demo.py plan-008557`` or ``8557``) —
  loads that real ResPlan plan and lands it in ``out/<plan-id>/``.

Every artifact (walls / panels / openings / framing / bom / sequences / model.ifc
/ summary.json) is written to the per-plan folder; the summary table is printed.
Use PipelineConfig(include_framing=False) for the walls-only "common cut".
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from floorplan_pipeline import PipelineConfig, run_pipeline, run_pipeline_for_plan

HERE = Path(__file__).parent.parent
EXAMPLES = HERE / "examples"
OUT_BASE = HERE / "out"

# The hero plan, so the pipeline demo tells the same one-house story as the
# per-repo demos (see wall-extract/scripts/demo.py DEMO_PLAN_ID).
DEMO_PLAN_ID = "plan-008557"

# framing member role -> IFC PredefinedType (mirrors aec-ifc-export mapping).
_PREDEF = {
    "bottom_plate": "PLATE", "top_plate": "PLATE",
    "standard_stud": "STUD", "king_stud": "STUD", "jack_stud": "STUD",
    "cripple_stud": "STUD", "header": "MEMBER", "sill": "MEMBER",
}


def _member_breakdown(out_dir: Path) -> str:
    framing_file = out_dir / "framing.json"
    if not framing_file.exists():
        return ""
    counts: Counter = Counter()
    for framing in json.loads(framing_file.read_text()):
        for m in framing["members"]:
            counts[_PREDEF.get(m["role"], "MEMBER")] += 1
    parts = " / ".join(f"{counts[k]} {k}" for k in ("STUD", "PLATE", "MEMBER") if counts[k])
    return f"  ({parts})"


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg in (None, "synthetic", "pipeline-000"):
        # Synthetic plan: id 'pipeline-000', lands in out/pipeline-000/.
        rooms = json.loads((EXAMPLES / "input_rooms.json").read_text())["rooms"]
        plan_id = "pipeline-000"
        out_dir = OUT_BASE / plan_id
        summary = run_pipeline(rooms, PipelineConfig(out_dir=str(out_dir)), plan_id=plan_id)
    else:
        # Real ResPlan plan by id (e.g. 'plan-008557' or '8557').
        summary = run_pipeline_for_plan(arg, out_base=str(OUT_BASE))
        out_dir = OUT_BASE / summary["plan_id"]

    print("\n=== floorplan-pipeline end-to-end ===")
    print(f"plan:             {summary['plan_id']}")
    print(f"rooms:            {summary['rooms']}")
    print(f"walls:            {summary['walls']}")
    print(f"panels:           {summary['panels']}")
    print(f"openings:         {summary['openings']}")
    print(f"framing members:  {summary.get('framing_members', 0)}{_member_breakdown(out_dir)}")
    print(f"member sequences: {summary.get('member_sequences', 0)} panels sequenced")
    print(f"panel sequence:   {summary.get('panel_steps', 0)} steps")
    n_sp, n_sf = summary.get("skipped_panels", 0), summary.get("skipped_framing", 0)
    print(f"skipped units:    {summary.get('skipped', 0)} ({n_sp} panels, {n_sf} framing)")
    for sk in summary.get("skips", []):
        print(f"  - {sk['stage']}: {sk['id']} — {sk['reason']}")
    print(f"IFC:              {summary.get('ifc_path', '-')}  (valid: {summary.get('ifc_valid')})")
    print(f"\nArtifacts in {out_dir}/")


if __name__ == "__main__":
    main()
