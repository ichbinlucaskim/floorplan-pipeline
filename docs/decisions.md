# Architecture Decision Records — floorplan-pipeline

---

## ADR-001 — Thin orchestrator; domain logic stays in components

**Status:** accepted (2026-06-16)

**Context.** Six independent repos already implement extraction, decomposition,
framing, sequencing, IFC export, and the schema contract. The temptation in an
integration repo is to "just add" a bit of logic here.

**Decision.** This repo is a **thin orchestrator**. `stages.py` only calls
component functions and passes data through; `pipeline.py` only sequences the
stages and validates seams. No extraction/framing/sequencing logic is
reimplemented here. Components are installed as **editable local dependencies**
(`pip install -e ../<repo>`), so the orchestrator imports the real code.

**Why.** Professional multi-repo composition keeps each component independently
owned, tested, and swappable; the orchestrator owns *flow + integration tests*,
not domain rules. Duplicating logic here would create two sources of truth.

**Consequences.** A fresh clone needs the sibling repos present (this is a
local-integration repo, not a PyPI package). `stages.py` stays auditable as
pure wiring — if it grows domain logic, that's a smell to push back into a
component.

---

## ADR-002 — Validate at every seam

**Status:** accepted (2026-06-16)

**Decision.** Every stage output is schema-validated (`validate_wall`,
`validate_panel`, `validate_framing`, `validate_bom`, `validate_sequence`) before
the next stage consumes it; the final IFC is checked with `ifcopenshell.validate`.
A contract break **fails loud**.

**Why.** Catching a seam break *at the seam* (with the offending artifact named)
is the entire value of an integration repo. The aec-schema contract is the
coupling between components, so it is exactly where regressions surface.

**Consequences.** The end-to-end test is also a contract test: if any component
changes its output shape incompatibly, the pipeline fails immediately rather than
producing a subtly-wrong IFC.

---

## ADR-003 — Two cuts via config (framing on/off)

**Status:** accepted (2026-06-16)

**Decision.** `PipelineConfig.include_framing` (plus `include_sequence`,
`include_ifc`) selects between two product cuts from one codebase:
- **framing on** — full chain: framing + sequence + `IfcElementAssembly`.
- **framing off** — walls + openings IFC only.

Both must produce a **valid** IFC (verified in tests).

**Why.** The same pipeline serves a panelized-manufacturing audience (needs the
framing) and a wall/IFC-interoperability audience (needs only walls + IFC) without
forking the code — toggling a flag, not maintaining two pipelines.

**Consequences.** Tests cover both modes; the walls-only path must remain valid
even as framing evolves.

---

## ADR-004 — Real-ResPlan ingestion adapter, per-plan output, resilient stages

**Status:** accepted (2026-06-17)

**Context.** The pipeline ran end-to-end only on the synthetic
`examples/input_rooms.json`. A real ResPlan record is
`{room_type_key: Polygon | MultiPolygon}` in pixel coordinates, keyed by an
integer `id` — a different shape from the `rooms` list `run_pipeline` ingests.
Two real-plan failure modes also surfaced: some plans contain a wall whose
opening layout admits no panel split under `MAX_PANEL_LENGTH_MM`, which raised an
**uncaught** `ValueError` and killed the whole run.

**Decision.**
1. **Adapter** (`resplan_input.py`): `record_to_rooms` explodes each geometry,
   keys polygon *i* of `base` as `f"{base}_{i}"`, and carries its exterior ring.
   `load_resplan_plan(plan_id)` loads a record **by id** (not `records[0]`);
   `run_pipeline_for_plan(plan_id)` runs it end-to-end. Pixel→mm scaling is **not**
   duplicated here — `wall-extract` owns the single `PX_TO_MM` constant.
2. **Per-plan output** — artifacts go to `out/<plan-id>/` (e.g. `out/plan-008557/`),
   so runs are real and reusable. The synthetic example is not special-cased: its
   id is `pipeline-000`, so it lands in `out/pipeline-000/`. A `summary.json`
   (stage counts + skips + validation) is written alongside.
3. **Skip-with-warning for `stage_panels`** (option B) — a wall that can't be
   panelized is logged as a warning and skipped, mirroring `stage_framing`'s
   existing handling of out-of-envelope panels. Both stages append skipped units
   to a `skips` list the pipeline reports in the summary (`skipped`,
   `skipped_panels`, `skipped_framing`, `skips`) — accounted, not silently
   dropped. A single bad unit yields a **partial but valid** IFC instead of
   crashing the run.

**Why.** This is wiring, not geometry work: the chosen plans already produce
correct IFC. Resilience matches the project's "fail loud on contract breaks, but
degrade gracefully on documented domain limits" stance — a domain limit
(over-length panel run, opening too tall) is not a seam break.

**Role boundary.** Building the pipeline, adapter, I/O, and IFC generation is our
(AI/SWE) lane. The *standards* the output must follow — naming conventions,
coordinate origin, property sets (Psets), classification (OmniClass) — are what a
**BIM Coordinator** owns via a BIM Execution Plan (BEP). There is no BEP in this
portfolio, so we pick sensible, **documented defaults** (plan-id `plan-{id:06d}`,
per-plan folder naming, mm throughout, single origin) and say they are defaults.
We deliberately do **not** invent a Pset/classification scheme — that is
Coordinator scope.

**Consequences / honest scope.** The output contains **walls + framing**, not
`IfcSpace` (rooms are consumed to derive walls, not re-emitted as spaces). Two
characterized, non-blocking items remain (see README "Known items"): one
`front_door` per plan is dropped because `wall-extract`'s `OPENING_KEYS` is
`{door, window}`; and a small, bounded number of short `sill` members tessellate
to zero verts in `ifcopenshell.geom` while keeping valid placements.
