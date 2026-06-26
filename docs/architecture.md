# Architecture — floorplan-pipeline

The end-to-end system: a room-plan polygon becomes manufacturing-ready output
(wall segments, transport panels, light-wood framing, a fabrication sequence, and
a valid IFC4 model) by composing **six independent repos** over **one JSON-Schema
contract layer**.

## Pipeline

```
                                   ┌──────────────────────┐
 room polygons ──▶ wall-extract ──▶│      aec-schema      │
   (pixels)         (L1)           │  (JSON contracts)    │
                       │           └──────────────────────┘
                       ▼                     ▲  validates every seam
                 panel-decompose (L2-a)      │
                       │                     │
                       ▼                     │
                 framing-synth (L2-b) ───────┤
                       │                     │
            ┌──────────┴───────────┐         │
            ▼                      ▼          │
   assembly-sequence (L2-c)   aec-ifc-export ─┘
   (fabrication order DAG)    (IFC4: IfcElementAssembly + IfcMember)
```

`floorplan-pipeline` is the thin orchestrator: it owns the flow and the
integration tests, **not** the domain logic (that lives in each component).

## Stage contracts (aec-schema types)

| Stage | Repo | Input → Output | Schema at the seam |
|---|---|---|---|
| Wall extraction | `wall-extract` (L1) | room polygons → wall segments (+ opening geometry) | `wall.schema.json`, `opening.schema.json` |
| Panel decomposition | `panel-decompose` (L2-a) | walls → transport panels (≤3600mm) (+ panel-local openings) | `panel.schema.json` |
| Framing synthesis | `framing-synth` (L2-b) | panel + openings → studs/plates/headers (+ BOM) | `framing.schema.json`, `bom.schema.json` |
| Assembly sequence | `assembly-sequence` (L2-c) | framing/panels → fabrication order (DAG) | `sequence.schema.json` |
| IFC export | `aec-ifc-export` | walls+openings+framing+panels → IFC4 | (IFC4, not JSON) |
| Data contract | `aec-schema` | JSON Schema linking every stage | — |

### Two opening maps (an easy thing to get wrong)

Openings travel as **two** maps, by design:
- **wall-relative** (`wall-extract` output) → consumed by `aec-ifc-export`,
  because IFC `IfcOpeningElement`s void into the **wall** (`IfcRelVoidsElement`).
- **panel-local** (`panel-decompose` `return_openings=True`) → consumed by
  `framing-synth`, because framing is laid out in **panel** coordinates.

The orchestrator keeps both and routes each to the right consumer; it never
re-derives geometry. Units are **millimetres throughout** (aec-ifc-export ADR-003).

## Why modular (not one model)

Each stage is an independent, swappable product linked only by aec-schema JSON
contracts. A customer can replace any single component (a different extractor, a
different framing rule set) without touching the others — the contract is the only
coupling. This mirrors how parts compose in real prefab / Factory-as-a-Service
systems, where the pipeline is assembled from replaceable units rather than a
monolith.

Concretely, the same codebase serves two audiences by toggling one config flag
(`include_framing`):
- **framing on** → studs/plates/headers + sequence + `IfcElementAssembly`
  (panelized-manufacturing audience).
- **framing off** → walls + openings IFC only (wall/IFC-interoperability audience).

## Scope boundary (ML/SWE vs. engineering) — at the system level

The pipeline owns **data-model correctness and interoperability**. It deliberately
does **not** make engineering judgments — those stay with engineers:

- **No structural verification.** Member sizing is a prescriptive IRC
  simplification (framing-synth `framing_rules.md`), not engineered design —
  PE-stamped scope.
- **No sequence optimization.** assembly-sequence produces a *valid* fabrication
  order, not a robot-path/time/cost-*optimal* one — that needs factory data and
  is Promise Robotics' core IP.

These boundaries are a feature: the system is correct and complete where software
should be, and defers where licensed engineering judgment is required.

## Component repos

- [aec-schema](https://github.com/ichbinlucaskim/aec-schema) — JSON-Schema contract layer.
- [wall-extract](https://github.com/ichbinlucaskim/wall-extract) — room polygons → wall segments.
- [panel-decompose](https://github.com/ichbinlucaskim/panel-decompose) — walls → transport panels.
- [framing-synth](https://github.com/ichbinlucaskim/framing-synth) — panels → framing + BOM.
- [assembly-sequence](https://github.com/ichbinlucaskim/assembly-sequence) — framing → fabrication order.
- [aec-ifc-export](https://github.com/ichbinlucaskim/aec-ifc-export) — everything → IFC4.
