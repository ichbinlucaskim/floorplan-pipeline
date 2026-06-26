# floorplan-pipeline

> **End-to-end: room plan → wall framing → IFC + assembly sequence.**
> A modular AEC pipeline of six independent, schema-linked components.

<!-- [30s demo GIF here] — see scripts/make_demo_video.md -->

## What this is

One command turns a room-plan polygon into manufacturing-ready output: wall
segments, transport panels, light-wood framing (studs / plates / headers), a
fabrication / assembly sequence, and a valid **IFC4** model that opens in any BIM
viewer. **No Revit.**

```bash
make demo
# rooms → … → out/pipeline-000/model.ifc
#
# === floorplan-pipeline end-to-end ===
# plan:             pipeline-000
# rooms:            6
# walls:            10
# panels:           13
# openings:         3
# framing members:  155  (111 STUD / 39 PLATE / 5 MEMBER)
# member sequences: 13 panels sequenced
# panel sequence:   13 steps
# skipped units:    0 (0 panels, 0 framing)
# IFC:              out/pipeline-000/model.ifc  (valid: True)
```

## The system

```
room polygons → wall-extract → panel-decompose → framing-synth ┬→ aec-ifc-export
                                                               └→ assembly-sequence
        (every seam is an aec-schema JSON contract, validated in-flight)
```

| Stage | Repo | Input → Output |
|---|---|---|
| Wall extraction | [wall-extract](https://github.com/ichbinlucaskim/wall-extract) | room polygons → wall segments |
| Panel decomposition | [panel-decompose](https://github.com/ichbinlucaskim/panel-decompose) | walls → transport panels |
| Framing synthesis | [framing-synth](https://github.com/ichbinlucaskim/framing-synth) | panels → studs/plates/headers + BOM |
| Assembly sequence | [assembly-sequence](https://github.com/ichbinlucaskim/assembly-sequence) | framing → fabrication order (DAG) |
| IFC export | [aec-ifc-export](https://github.com/ichbinlucaskim/aec-ifc-export) | all → IFC4 (`IfcElementAssembly` + `IfcMember`) |
| Data contract | [aec-schema](https://github.com/ichbinlucaskim/aec-schema) | JSON Schema linking every stage |

See [`docs/architecture.md`](docs/architecture.md) for the per-stage contracts
and the two-opening-map data flow.

## Why modular (not one model)

Each stage is an independent, swappable product linked only by aec-schema JSON
contracts — so a customer can replace any component (a different extractor, a
different framing rule set) without touching the rest. This mirrors how parts
compose in real prefab / Factory-as-a-Service systems: the pipeline is *assembled*
from replaceable units, not a monolith. The orchestrator itself is **thin** — it
wires stages and validates seams; all domain logic stays in the components
([ADR-001](docs/decisions.md)).

One flag serves two audiences:

```python
from floorplan_pipeline import run_pipeline, PipelineConfig

run_pipeline(rooms, PipelineConfig(include_framing=True))   # full: framing + sequence + IFC
run_pipeline(rooms, PipelineConfig(include_framing=False))  # walls-only IFC (interoperability cut)
```

## Run it

```bash
make setup     # installs the six sibling repos editable, then this package
make demo      # synthetic plan → out/pipeline-000/model.ifc (validated)
make test      # end-to-end + per-seam contract tests + IFC-valid test
make lint      # ruff
```

> Fresh-clone note: this is a **local-integration** repo, not a PyPI package. The
> five component repos must be present as sibling folders (`../wall-extract`, …);
> `make setup` installs each editable.

### Run a real ResPlan plan

The synthetic demo is self-contained, but the pipeline also runs any real
[ResPlan](../data/resplan) plan **by id** via the ingestion adapter
([ADR-004](docs/decisions.md)):

```python
from floorplan_pipeline import run_pipeline_for_plan

# 'plan-008557' (the portfolio hero: a 7-room, 3-bed house) or the bare id 8557
summary = run_pipeline_for_plan("plan-008557")
# → out/plan-008557/{walls,panels,openings,framing,bom,
#                    member_sequences,panel_sequence}.json, model.ifc, summary.json
```

…or from the demo script:

```bash
python scripts/demo.py plan-008557   # real plan → out/plan-008557/
python scripts/demo.py               # synthetic → out/pipeline-000/
```

**Output convention (a sensible default).** Every run writes its artifacts to
`out/<plan-id>/`, so runs are real and reusable; the synthetic plan is not
special-cased (`pipeline-000` → `out/pipeline-000/`). In real practice the folder
naming, coordinate origin, and Pset/classification standards would be dictated by
a **BIM Coordinator** in a BIM Execution Plan — there is none here, so we use
documented defaults (`plan-{id:06d}`, mm throughout, single origin) rather than
invent a standard. The output contains **walls + framing**, *not* `IfcSpace`
(rooms are consumed to derive walls, not re-emitted as spaces).

### Resilience: skip-with-warning on domain limits

A seam (schema) break **fails loud** ([ADR-002](docs/decisions.md)), but a
*documented domain limit* does not kill the run. If a wall's opening layout admits
no panel split under `MAX_PANEL_LENGTH_MM` (`stage_panels`), or a panel's opening
falls outside framing-synth's prescriptive envelope (`stage_framing`), that single
unit is logged as a warning and **skipped** — the run continues and still emits a
**partial but valid** IFC. Skips are counted and reported in `summary.json`
(`skipped`, `skipped_panels`, `skipped_framing`, `skips`), never silently dropped.

### Known items (characterized, non-blocking)

- **One `front_door` per plan is dropped.** `wall-extract`'s `OPENING_KEYS` is
  `{door, window}`, so a `front_door` polygon isn't assigned to a wall (e.g.
  hero plan: 15 source openings → 14 hosted). What counts as a hosted opening is
  `wall-extract`'s domain decision, so this is logged rather than patched here.
- **A few short `sill` members tessellate to 0 verts** in `ifcopenshell.geom`
  (8 of 469 on the hero, all `sill`s) — an engine quirk; the members keep valid
  `ObjectPlacement`s. `IfcElementAssembly` containers are intentionally
  geometry-less. Walls and all other members tessellate fully.

## Scope boundary (what this is NOT)

- **No structural verification** — member sizing is a prescriptive IRC
  simplification, not engineered design (PE scope).
- **No sequence optimization** — produces a *valid* order, not a robot-path-optimal
  one (needs factory data; out of scope).

These boundaries are deliberate: the pipeline owns data-model correctness and
interoperability; engineering judgment stays with engineers. See
[`docs/architecture.md`](docs/architecture.md#scope-boundary-mlswe-vs-engineering--at-the-system-level).

## Built with

Python, Shapely, NetworkX, IfcOpenShell. Data: ResPlan (MIT).
