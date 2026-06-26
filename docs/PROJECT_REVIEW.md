# Project Review — AEC Framing Pipeline (7 repos)

A critical, honest bar-check of the whole system (aec-schema, wall-extract,
panel-decompose, framing-synth, assembly-sequence, aec-ifc-export,
floorplan-pipeline) against three lenses. The goal is to surface real weaknesses,
not to validate. Status at review time: **195 tests pass across 7 repos**; the
end-to-end IFC validates (schema) and now renders correctly in world space.

---

## Lens 1 — Professional software engineering

**Verdict: Strong (≈ senior-level structure) with real, nameable gaps. ~B+/A-.**

### Strengths (concrete)
- **Architecture.** Six processing repos decoupled by one JSON-Schema contract
  layer (`aec-schema`). The coupling is the schema, not imports — components are
  genuinely swappable. `floorplan-pipeline/stages.py` is verifiably thin (only
  calls component functions; grep-clean of domain logic).
- **Tests assert behavior, not "it runs."** Examples: `assembly-sequence`'s DAG
  cycle-detection + determinism (`test_dag.py`), framing-synth's stud-skip vs
  opening geometry, `aec-ifc-export/tests/test_geometry_placement.py` checking
  **world** coordinates, schema validation **at every seam** in the pipeline.
- **ADRs** record non-obvious decisions *and* corrections (ADR-005 openly retracts
  an earlier overstated geometry claim). That honesty is itself a quality signal.
- **Hygiene.** `ruff` clean across all repos, `py.typed` + type hints, per-repo CI,
  deterministic output (lexicographic topo sort), editable multi-repo installs.

### Gaps a reviewer would flag (ranked)
1. **Recurring "checks pass but the real artifact is wrong" class of bug.** Several
   times the schema validated (or a hand-rolled check passed) while the real output
   was wrong or *looked* wrong: the mm/m unit bug, NULL wall bodies, origin-stacked
   framing, and a false "still collapsed" alarm caused by a row-major read of a
   column-major matrix. Each was caught *reactively*. The honest read: schema
   validation and ad-hoc inspection were over-trusted as proxies for correctness.
   **Partially closed (reactively, 2026-06-16):** a **golden end-to-end test**
   (`floorplan-pipeline/tests/test_golden_endtoend.py`) now opens the real
   `model.ifc` and asserts world-space correctness via the **authoritative**
   `ifcopenshell.util.placement.get_local_placement` (no hand-rolled matrix math) —
   no NULL walls, framing follows the wall footprint, panels at distinct locations,
   IFC valid. See aec-ifc-export ADR-006. This is the guard that should have existed
   from the start; it exists now, but the pattern remains the top lesson.
2. **One member fails to tessellate** (154/155 in the integrated demo). Originally
   mis-attributed to a degenerate ~84 mm cripple; it is actually a **valid 760 mm
   sill** (m017) with a sound placement that `ifcopenshell.geom` returns 0 verts for
   — an engine quirk, not a data defect. **Now bounded** by a characterization test
   (empty tessellations ≤ 2, and they must still have valid placements), and all
   verts-based tooling skips 0-vert shapes (no NaN). Tracked, not silently tolerated;
   the underlying engine cause is still open but does not affect IFC correctness.
3. **Cross-repo CI is aspirational.** `floorplan-pipeline/.github/workflows/ci.yml`
   needs a workspace checkout of all siblings; as written it won't run on an
   isolated clone. There is no CI that actually proves the integration in the cloud.
4. **Silent skips.** `stages.stage_framing` swallows `ValueError` and drops a panel
   with only a warning. Defensible for demo robustness, but in a pipeline this can
   mask real regressions — it should at least surface a count in the summary and be
   toggleable (fail-fast mode).
5. **Coverage blind spots.** `visualise.py`, `demo.py`, and `aec-ifc-export/spaces.py`
   (unused) are untested; no coverage gate in CI despite `pytest-cov` being a dep.
6. **Reproducibility.** All versions pinned at `0.1.0`, no release/tagging; a fresh
   clone depends on exact sibling layout. Fine for a portfolio, not for distribution.

---

## Lens 2 — IFC standard correctness (beyond `ifcopenshell.validate`)

**Verdict: Schema-correct and now geometrically correct; not yet MVD-conformant.
~B.**

`ifcopenshell.validate` only checks schema, so "0 errors" is necessary, not
sufficient — a point this project learned the hard way (ADR-003, ADR-005, and the
diagonal-walls bug below). Each was schema-valid but geometrically wrong, found
late via a visual check + standard verification, not by validation.

**Opening voids (found + fixed, 2026-06-16).** Openings were related to walls but
the wall body wasn't cut in Reference-View viewers, and where it *was* cut it was
a 60 mm notch (the opening centred on the wall face, not its thickness centre).
Fixed by centring the void on the wall thickness (true through-hole) and **baking**
the cut into the body (`IfcBooleanResult`) so it shows across viewers, keeping the
`IfcRelVoidsElement` for semantics (ADR-008). The fix was slowed badly by trusting
`ifcopenshell.geom.create_shape` (returns 0 verts for these bodies); the geometry
**iterator** — what viewers use — was correct all along. Same measurement-trap
class as ADR-006. Honest read: found by eyeballing a viewer, and the right test
oracle (the iterator) was adopted only after a long detour.

**Wall orientation (found + fixed, 2026-06-16).** 6 of 10 walls rendered
**diagonal** despite an orthogonal input — an IfcOpenShell 0.8.x bug in
`create_2pt_wall` (it unit-converts `p1` but not `p2` when `is_si=False`, mixing
units; see `aec-ifc-export/docs/KNOWN_LIBRARY_ISSUES.md` LIB-001). Fixed by setting
the wall placement with our own mm matrix (ADR-007); a golden orthogonality
assertion now guards it. Notably this is the **second** IfcOpenShell placement
quirk bypassed (after the relative-placement 1000× issue, ADR-005) — the project
now sets **all** placements (walls and framing) via its own explicit mm matrices,
trusting the library helpers less. Honest read: this was caught by eyeballing the
viewer, not by tests — the orthogonality check existed nowhere until after.

### Correct per buildingSMART IFC4.3
- **Spatial structure** Project→Site→Building→Storey with `IfcRelAggregates`
  containment [[1]](#sources).
- **Framing mapping** panel→`IfcElementAssembly`, members→`IfcMember` with real
  `IfcMemberTypeEnum` values `STUD`/`PLATE`, aggregated via `IfcRelAggregates`
  [[2]](#sources) — the premanufactured-assembly use is the canonical one.
- **Openings** `IfcOpeningElement` + `IfcRelVoidsElement` [[3]](#sources).
- **Units** SI millimetre (`IfcSIUnit .MILLI. .METRE.`), consistent throughout.
- **Walls** now carry `IfcShapeRepresentation` bodies; **placements are valid** —
  absolute world placement is explicitly permitted ("if `PlacementRelTo` is not
  given, the product is placed absolutely in the world coordinate system")
  [[4]](#sources).

### Gaps / what a stricter reviewer (or an MVD checker) would flag
1. **Placement convention, not just validity.** buildingSMART's convention is that
   an element "shall be placed relative to the local placement of its container"
   [[4]](#sources). Members here are **absolute** (`PlacementRelTo = None`) — valid,
   but not the recommended relative chain (storey→wall→assembly→member). This was a
   deliberate trade to dodge a 0.8.x relative-placement unit quirk (ADR-005);
   honest, but a Coordination/Reference-View MVD check may prefer the relative form.
2. **No material layer set on walls.** Walls have a body but no
   `IfcMaterialLayerSetUsage`; a "proper" wall carries its layered build-up. Only
   framing members carry a (placeholder) material.
3. **No MVD conformance claim.** The output is validated against the schema, not
   against the Reference View / Coordination View model view definitions that real
   BIM exchanges require — so "opens in a viewer" ≠ "certified interoperable."
4. **Opening boolean is relational only.** The void is expressed via
   `IfcRelVoidsElement`; whether a given viewer renders the hole depends on it
   applying the boolean — worth verifying in target viewers, not assumed.
5. **Single storey**, no sheathing element (`IfcPlate`/`IfcCovering`), assembly has
   no own placement (pure logical container). All acceptable simplifications, but
   each is a real-model gap.

---

## Lens 3 — Real-world usability (would a practitioner call this usable?)

**Verdict: A genuinely usable *interoperability + data-model* layer; an explicitly
*non-engineered* framing layer. Portfolio-grade overall, with production-usable
seams.**

### Production-usable today
- The **schema-contract architecture** and the **deterministic, validated pipeline**
  are the real asset — a practitioner could drop in a different extractor or framing
  rule set behind the same contracts. This is the genuinely reusable idea.
- The **IFC export** now produces walls + framing at correct world positions that
  open in any IFC4 viewer with no Revit — a real interoperability win for a shop
  that wants to *see* and *exchange* panelized framing.

### Portfolio-grade (honest gaps to production)
- **Framing is a prescriptive IRC simplification**, not engineered design — header
  tiers, single species, no load path. Correct as a *data model*, not a *structural*
  one (framing-synth makes this explicit).
- **Assumed inputs.** Opening heights (door 2032 / window 1200), sill 900 mm, wall
  thickness, and the global `PX_TO_MM = 38` scale are **defaults**, not measured.
  Real plans need calibration and real opening dimensions; the px→mm constant is the
  single most fragile real-world assumption.
- **Material is a placeholder**; species/grade is a domain-expert input by design.
- **Sequence is valid, not optimal** — no robot-path/time/cost objective (needs
  factory data).
- **No connections/fasteners, tolerances, or fabrication metadata** — a real
  cut-list/CAM consumer would need these.

### The honest ML/SWE-vs-engineering line
The project is precise about its boundary, and that precision is a strength: it
owns **data-model completeness and interoperability** (extraction → panels →
framing data → sequence → valid IFC) and explicitly **defers** structural
verification, species/grade, and sequence optimization to licensed engineers /
systems with the data. That is the correct scope for an ML/SWE portfolio — the
gap to production is real and *named*, not hidden.

---

## Bottom line
A well-architected, honestly-scoped system whose **modular schema-contract design**
and **post-bug world-space testing** are its strongest signals, and whose **recurring
"valid-but-wrong" failure mode** is the clearest lesson. Production-usable as an
interoperability/data layer; portfolio-grade (by explicit choice) as an engineering
artifact.

## Sources
1. buildingSMART IFC4.3 — Spatial composition / `IfcRelAggregates`, `IfcBuildingStorey`:
   https://standards.buildingsmart.org/IFC/RELEASE/IFC4_3/HTML/lexical/IfcRelAggregates.htm
2. buildingSMART IFC4.3 — `IfcElementAssembly`, `IfcMember` / `IfcMemberTypeEnum`:
   https://standards.buildingsmart.org/IFC/RELEASE/IFC4_3/HTML/lexical/IfcMemberTypeEnum.htm
3. buildingSMART IFC4.3 — `IfcRelVoidsElement`:
   https://standards.buildingsmart.org/IFC/RELEASE/IFC4_3/HTML/lexical/IfcRelVoidsElement.htm
4. buildingSMART IFC4.3 — `IfcLocalPlacement` (PlacementRelTo convention; absolute
   placement when not given):
   https://ifc43-docs.standards.buildingsmart.org/IFC/RELEASE/IFC4x3/HTML/lexical/IfcLocalPlacement.htm
