"""
Real-ResPlan ingestion adapter (ADR-004).

Bridges a raw ResPlan record — ``{room_type_key: Polygon | MultiPolygon}`` in
pixel coordinates — to the ``rooms`` list (``[{"id", "points"}, ...]``) that
:func:`run_pipeline` ingests. The shipped pipeline was otherwise hard-wired to
the synthetic ``examples/input_rooms.json``; this is the missing path that lets a
real plan run end-to-end.

Conventions (sensible defaults — a real project's BIM Execution Plan would
normally dictate these; we document ours rather than invent a standard):

* **Plan id**: ResPlan record ids are bare integers (e.g. ``8557``). We render
  them as ``plan-{id:06d}`` (e.g. ``plan-008557``), matching the scheme already
  used by ``wall-extract/scripts/demo.py``.
* **Pixel→mm scaling** is *not* done here. Pixel coordinates are carried through
  verbatim; ``wall-extract`` owns the single ``PX_TO_MM`` constant and applies it
  during extraction. We never duplicate or pre-apply that conversion.
"""
from __future__ import annotations

import dataclasses
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon

from .config import PipelineConfig
from .pipeline import run_pipeline

# Default base directory for per-plan output folders (Part 3 / ADR-004).
DEFAULT_OUT_BASE = "out"

_PLAN_ID_RE = re.compile(r"(\d+)")


def plan_id_str(record_id: int | str) -> str:
    """Canonical plan id for a ResPlan record id: ``8557`` -> ``'plan-008557'``."""
    return f"plan-{int(record_id):06d}"


def _record_id(plan_id: int | str) -> int:
    """Parse an int record id from either ``8557`` or ``'plan-008557'``."""
    if isinstance(plan_id, int):
        return plan_id
    m = _PLAN_ID_RE.search(str(plan_id))
    if not m:
        raise ValueError(f"could not parse a ResPlan record id from {plan_id!r}")
    return int(m.group(1))


def _find_loader_dir() -> Path:
    """Locate the repo-level ``data/resplan`` loader directory.

    Walks up from this file (works from a source checkout) so the adapter does
    not hard-code an absolute path. Raises a clear error if the dataset loader
    cannot be found.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data" / "resplan" / "loader.py"
        if candidate.exists():
            return candidate.parent
    raise FileNotFoundError(
        "data/resplan/loader.py not found above "
        f"{Path(__file__).resolve()} — is the ResPlan dataset checked out?"
    )


@lru_cache(maxsize=1)
def _load_records_by_id() -> dict[int, dict[str, Any]]:
    loader_dir = _find_loader_dir()
    if str(loader_dir) not in sys.path:
        sys.path.insert(0, str(loader_dir))
    from loader import load_resplan  # type: ignore[import-not-found]

    return {int(r["id"]): r for r in load_resplan()}


def record_to_rooms(record: dict[str, Any]) -> list[dict]:
    """Explode a raw ResPlan record into the pipeline's ``rooms`` list.

    Each geometry value is exploded into its constituent polygons; polygon *i*
    of key ``base`` is keyed ``f"{base}_{i}"`` and carries that polygon's
    exterior ring as ``points``. Non-geometry values (ints, ``neighbor`` graph,
    etc.) are skipped, as are empty polygons. ``wall-extract`` later filters keys
    by its own ``ROOM_KEYS`` / ``OPENING_KEYS``, so carrying extra keys (e.g.
    ``land``, ``inner``) is harmless — we don't second-guess its classification.
    """
    rooms: list[dict] = []
    for key, val in record.items():
        if not isinstance(val, (Polygon, MultiPolygon)):
            continue
        geoms = list(val.geoms) if isinstance(val, MultiPolygon) else [val]
        for i, geom in enumerate(geoms):
            if geom.is_empty:
                continue
            rooms.append(
                {"id": f"{key}_{i}", "points": [list(c) for c in geom.exterior.coords]}
            )
    return rooms


def load_resplan_plan(plan_id: int | str) -> tuple[str, list[dict]]:
    """Load a ResPlan plan *by id* and adapt it to the pipeline's ``rooms`` list.

    Parameters
    ----------
    plan_id:
        Either a bare record id (``8557``) or a canonical plan id
        (``'plan-008557'``).

    Returns
    -------
    ``(plan_id_str, rooms)`` — the canonical id (for output folder + wall ids)
    and the adapted rooms list.
    """
    rid = _record_id(plan_id)
    records = _load_records_by_id()
    if rid not in records:
        raise KeyError(f"ResPlan record id {rid} not found ({len(records)} records loaded)")
    return plan_id_str(rid), record_to_rooms(records[rid])


def run_pipeline_for_plan(
    plan_id: int | str,
    config: PipelineConfig | None = None,
    *,
    out_base: str = DEFAULT_OUT_BASE,
) -> dict:
    """Load a real ResPlan plan by id and run it end-to-end.

    Artifacts are written to ``{out_base}/{plan_id}/`` (e.g.
    ``out/plan-008557/``) — a per-plan folder so runs are real and reusable. The
    ``config.out_dir`` is overridden with this derived path; everything else in
    ``config`` is respected.

    Returns the pipeline summary dict (also written to ``summary.json``).
    """
    pid, rooms = load_resplan_plan(plan_id)
    config = config or PipelineConfig()
    config = dataclasses.replace(config, out_dir=str(Path(out_base) / pid))
    return run_pipeline(rooms, config, plan_id=pid)
