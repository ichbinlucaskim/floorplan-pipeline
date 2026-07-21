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

## ADR-005 — Byte-stable golden lock of pipeline output (before the service layer)

**Context.** A persistence and service layer (`floorplan-service`) will wrap the
pipeline. Before it is built we must lock what `run_pipeline` produces today, so
any behavioral drift introduced by the wrapper fails a test. The existing golden
tests (`test_golden_endtoend.py`, `test_artifacts_valid.py`) assert IFC
*geometry* and validity; they do **not** notice a change to the JSON artifacts
the pipeline emits, which is precisely the data the service will project into a
database. That is the gap this ADR closes.

**Decision.** `tests/test_golden_pipeline_000.py` runs the real pipeline for the
committed synthetic plan (`pipeline-000`, input `examples/input_rooms.json`, so it
is reproducible from the repo alone with no ResPlan dataset) and asserts:

1. The seven JSON artifacts (`walls`, `openings`, `panels`, `framing`, `bom`,
   `member_sequences`, `panel_sequence`) are **byte-identical** to committed
   golden fixtures in `tests/golden/pipeline-000/`.
2. `summary.json` is byte-identical **after** normalizing one field: the
   `ifc_path` value, which embeds the absolute output directory (environment- and
   run-dependent). Nothing else in the summary is normalized.
3. `model.ifc` matches a committed **structural signature** (IFC schema,
   validation error count, per-entity-type counts), not its bytes.

**Why `model.ifc` is not byte-locked.** Measured directly: two runs of the same
input differ on 430 of 2677 lines even after normalizing the header timestamp and
every GlobalId. The residual variation is IfcOpenShell emitting a random GlobalId
per entity, a wall-clock header timestamp, nondeterministic set ordering
(`IfcUnitAssignment`, aggregation sets), and nondeterministic instance-id (`#N`)
numbering. None are values the pipeline controls or that should be stable.
Byte-locking would require a full IFC canonicalizer (re-number every instance in a
canonical order, sort every set) -- fragile, large, and it would guarantee nothing
the geometry/validity tests do not already cover. The structural signature is
deterministic across runs (verified: identical between two runs) and catches the
regression that matters here: a change in *what entities* the pipeline emits.

**Rejected alternatives.**
* *Lock `model.ifc` bytes with a canonicalizer* -- rejected as over-engineering for
  no coverage gain over the signature plus existing geometry tests.
* *Assert only spot-checked JSON fields* -- rejected; a byte-stable lock is the
  point. Spot-checks let unasserted fields drift silently.
* *Use a ResPlan plan (e.g. the hero) as the golden* -- rejected; the ResPlan
  dataset is uncommitted (`data/` is gitignored), so the lock would not be
  reproducible in CI or from the repo alone. `pipeline-000` runs unconditionally.

**Consequences.** Regenerating the goldens is a deliberate act (re-run and commit),
so a diff to `tests/golden/` in a future PR is a visible, reviewable signal that
pipeline output changed. This is the single permitted change to `floorplan-pipeline`
in Stage 1: new tests and fixtures only, no source change.

## ADR-006 — Surface IFC validation statements (additive extension of _ifc_is_valid)

**Context.** The forthcoming persistence layer needs the individual
`ifcopenshell.validate` statements (level, message, type, instance, attribute) to
populate a `validation_errors` table. Those statements are already computed inside
`_ifc_is_valid` and then discarded: the function collapses them to a single bool
that lands in `summary["ifc_valid"]`. The one call site
(`pipeline.py`, `summary["ifc_valid"] = _ifc_is_valid(ifc_path)`) and the tests
that assert `summary["ifc_valid"] is True` require the bool to stay a genuine
`bool`, and the Stage-1 golden lock byte-freezes `summary.json`, so no key may be
added to the summary.

**Decision.**
1. Add `IfcValidation(NamedTuple)` = `(is_valid: bool, statements: tuple[dict, ...])`.
2. Add `validate_ifc(path) -> IfcValidation`, which runs the validation once and
   returns both the verdict and the raw statements.
3. Reduce `_ifc_is_valid(path) -> bool` to `return validate_ifc(path).is_valid`.
   Its signature and return type are unchanged, so the single existing call site
   and every `is True` assertion keep working with no edit, and `summary.json`
   gains no key (golden lock intact).
4. Export `validate_ifc` and `IfcValidation` from the package so the service layer
   can obtain statements from a produced `model.ifc` without a second, divergent
   validation path (does not bypass the existing validation, reuses it).

**Latent bug corrected in passing (flagged for review).** The original filter was
`s.get("level") == "Error"` (capital E). ifcopenshell 0.8.5 logs every issue via
`logger.error(...)`, so real statements carry `level == "error"` (lowercase) and
the capital-E filter never matched: `_ifc_is_valid` returned `True` for *any*
file, including an invalid one. No test caught it because the pipeline only ever
validates its own valid output (zero statements, so both filters agree on
`True`). `validate_ifc` uses the correct lowercase `"error"`. All 215 existing
tests and the golden lock stay green because they never validate an invalid IFC;
the behavior differs only on genuinely invalid input, where returning `False` is
correct and is exactly what the persistence layer needs.

**Rejected alternatives.**
* *Change `_ifc_is_valid` to return the tuple directly* — rejected: it forces the
  call site and the `is True` assertions to change, violating the additive
  requirement.
* *Return a truthy object (e.g. a bool subclass carrying statements)* — rejected as
  a clever-but-surprising type; a NamedTuple on a separate function is clearer and
  keeps the bool wrapper honest.
* *Add the statements to `summary.json`* — rejected: breaks the Stage-1 byte-stable
  golden and bloats the summary with verbose validation payloads. The service
  re-derives statements from the artifact via `validate_ifc` instead.
* *Preserve the capital-E filter to guarantee zero behavior change* — rejected:
  surfacing statements while computing `is_valid` from a filter that can never
  match would ship a knowingly-wrong verdict, defeating the purpose.

## ADR-007 — Golden IFC signature validates at the full EXPRESS profile

**Context.** Stage 2 verification found that the Stage 1 golden IFC signature
computed `error_count` with the same capital-`"Error"` inline filter that Stage 2
identified as broken, at ifcopenshell's default profile, and compared it against a
golden generated with that same filter. It was self-referential: it would have
passed even if real errors existed, so the lock did not actually verify
error-freeness. Separately, the default profile does not run the IFC4 EXPRESS
WHERE rules, under which the exported IFC in fact had violations (fixed in
aec-ifc-export ADR-009).

**Decision.**
1. Compute `error_count` through the corrected `validate_ifc` (lowercase `"error"`,
   the actual level ifcopenshell emits), not an inline filter.
2. Validate at the full EXPRESS WHERE-rule profile. `validate_ifc` gained an
   additive keyword-only `express_rules: bool = False`; the signature calls
   `validate_ifc(path, express_rules=True)`. The default is unchanged, so
   `_ifc_is_valid`, the pipeline summary, and every existing `validate_ifc` caller
   behave exactly as before.
3. Record the profile in the signature itself with an `express_rules: true` key,
   so the fixture is self-documenting about what its `error_count` means.

**Why the strong profile, not the default.** The point of the lock is to protect a
claim ("0 IFC validation errors"). The default profile validates schema and
references but not the WHERE rules, so a "0" there is the weak claim. Locking at
`express_rules=True` means a reappearance of any WHERE-rule violation (for example
a future change that relabels a boolean body as `SweptSolid` again) fails this
test. Locking the strong claim is the whole reason to have the signature.

**Fixture change.** `tests/golden/pipeline-000/ifc_signature.json` gains one line,
`"express_rules": true`. The `error_count` value stays `0` and `entity_counts` is
byte-identical, because the aec-ifc-export fix is attribute-only (it relabels
representations and sets an owner-history date; it adds and removes no entities).
The `0` now means "0 errors under strict IFC4 conformance, corrected filter",
where before it meant "0 under a filter that could never match".

**Cross-repo ordering.** This signature passes only when the aec-ifc-export
WHERE-rule fix (ADR-009) is present. In this repo's CI, aec-ifc-export is checked
out at `main`, so the aec-ifc-export fix must merge to its `main` before this
change's CI goes green. Verified green locally with the fix installed editable.

**Rejected alternatives.**
* *Keep the default profile and only fix the filter casing* — rejected: still locks
  the weak claim and would miss WHERE-rule regressions.
* *Compute `error_count` with a corrected inline filter instead of `validate_ifc`* —
  rejected: duplicates the validation logic the package already exposes; the whole
  Stage 2 point was one validation path.
