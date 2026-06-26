# Coordinate Collapse Diagnosis

## Symptom (as reported)
- All 10 `IfcWall` have `Representation = NULL` — no 3D wall geometry.
- All 155 `IfcMember` "vertices collapse to a single point" (X=0, Y=0, Z=0–4).
- Viewer shows one stacked wall instead of 13 spread panels.
- `ifcopenshell.validate` = 0 errors.

## TL;DR — root cause

**This is NOT a floorplan-pipeline seam bug.** Every JSON stage (walls → panels →
framing) carries correct, spread-out **millimetre** coordinates. The collapse is
**two independent defects inside `aec-ifc-export`**, both of which are *also present
in aec-ifc-export's own 53-wall ResPlan demo* — so the report's premise ("the same
code produced correct geometry on ResPlan") is **false** (see Step 5).

- **Defect A — NULL wall bodies.** `aec-ifc-export/walls.py` calls
  `geometry.create_2pt_wall(...)` but **ignores its return value**. In IfcOpenShell
  0.8.x that call *returns* an `IfcShapeRepresentation` and does **not** attach it;
  the wall is left with `Representation = None`. No `assign_representation` is called.
- **Defect B — panel-local framing stacking.** `aec-ifc-export/framing.py` places
  every member at its **panel-local** start coordinate and never applies the
  panel's **world** position (`panel["start"]`/direction). So all 13 panels' framing
  is dumped into the same origin band (member placement `Y ∈ [0,38]` even though
  panels belong to walls at world `y = 0, 3040, 5700`).

## Input (`examples/input_rooms.json`)
- Format: list of `{"id", "points": [[x,y],…]}`, ResPlan-style **pixel** polygons.
- Ranges: **x ∈ [0,184], y ∈ [0,150]** — pixel-like (not metres). Non-zero, valid.
- wall-extract scales px→mm via `PX_TO_MM = 38.0` (so 100px → 3800mm). Correct.

## Stage-by-stage coordinate trace

| Stage | Sample coordinate | Collapsed? |
|---|---|---|
| input rooms (px) | `living_0 = [[0,0],[100,0],[100,80],[0,80]]`, ranges x[0,184] y[0,150] | no |
| `stage_walls` out | wall-000 `start{0,0} end{3800,0}`; wall-002 `start{0,3040} end{3800,3040}` | **no — good mm spread** |
| `stage_panels` out | panel `start{0,0} end{3600,0} len 3600` | **no — good** |
| `stage_framing` out | member `start{0,0,0} end{3600,0,0} len 3600` | no values, but **PANEL-LOCAL** (y≡0) |
| `export_ifc` input | walls/panels spread; framings panel-local (by framing.schema contract) | inputs fine |
| `model.ifc` walls | `Representation = None` (×10) | **YES (Defect A)** |
| `model.ifc` members | placement `X[0,3600] Y[0,38] Z[0,2400]` — every panel at y≈0 | **YES (Defect B, stacked)** |

Per-panel proof of Defect B (member-0 placement vs the panel's world origin):

| panel | panel world (start.x, start.y) | member placement (x,y,z) |
|---|---|---|
| wall-001-panel-000 | (3800, 0) | (1121, 0, 0) ← not at x=3800 |
| wall-002-panel-000 | (0, **3040**) | (1200, **0**, 38) ← not at y=3040 |
| wall-005-panel-000 | (6840, 0) | (3040, 0, 38) ← not at x=6840 |

Members sit at panel-local coordinates; the panel's world placement is dropped.

## Reconciling the reported "vertices collapse to X=0, Y=0, Z=0–4"
That measurement read `shape.geometry.verts` from `ifcopenshell.geom.create_shape`,
which are **local** coordinates (the world transform is kept separately in
`shape.transformation`). Local verts are *always* near the origin (a 38×140mm
profile extruded along local +Z), so "all collapse to a point" is a **measurement
artifact**. The *real* collapse is Defect B (panels share the origin band because
their world placement is never applied), plus Defect A (no wall bodies at all).
The "Z 0–4 looks like metres" note is also a red herring: `ifcopenshell.geom`
**always returns metres**, regardless of the file's unit. The file is correctly mm
(`IfcSIUnit .MILLI. .METRE.`), and wall height flows as `2438` mm with
`is_si=False` — **units are correct**, not the bug.

## Why validation missed it
`ifcopenshell.validate` checks **schema conformance**, not geometric sanity:
- `IfcWall.Representation` is **optional** → a NULL body is schema-valid.
- Member placements are well-formed `IfcLocalPlacement`s → valid even when they all
  land at the origin.
This is the same blind spot as the earlier mm/m unit bug: validation green ≠
geometry sensible. No existing test asserts coordinate **spread** or non-NULL wall
representation.

## Proposed fix (describe only — NOT implemented here)

Both fixes are in **`aec-ifc-export`** (not floorplan-pipeline):

1. **Defect A — assign the wall representation.** In `walls.py`, capture the
   `create_2pt_wall` return and attach it:
   ```python
   rep = ifcopenshell.api.geometry.create_2pt_wall(model, element=entity, ... , is_si=False)
   ifcopenshell.api.geometry.assign_representation(model, product=entity, representation=rep)
   ```
   Verified in isolation: this flips `wall.Representation` from `None` to a real
   `IfcProductDefinitionShape`.

2. **Defect B — place framing in the panel's world frame.** `export_panel_framing`
   already receives `panel`. Build the panel world placement once
   (origin = `panel["start"]` in mm, local-X = direction `start→end`, local-Z = up)
   and either (a) set it as the **assembly's** `ObjectPlacement` and make each
   member placement **relative** to the assembly (`PlacementRelTo = assembly`), or
   (b) compose `panel_world @ member_local` into each member's placement matrix.
   Option (a) is cleaner and matches the Wall→Panel→Member decomposition already in
   place. (Panel `y` through-wall offset is ~0; the key missing piece is the
   in-plane translation + rotation to the panel's wall.)

### Regression tests to add (would have caught this)
- **No NULL wall bodies:** `assert all(w.Representation is not None for w in model.by_type("IfcWall"))`.
- **Coordinate spread / no stacking:** tessellate (with world transform applied, e.g.
  `settings.set("use-world-coords", True)` or apply `shape.transformation`) and assert
  the overall geometry bounding box spans a realistic building size — e.g. for inputs
  with walls at distinct world-Y, assert member world-placement **Y range > 100mm**
  (currently 38mm → would fail and flag the stacking).
- **Per-panel placement sanity:** assert a panel's members are near its
  `panel["start"]` world position, not the global origin.

## Scope note
The collapse is entirely in `aec-ifc-export`'s geometry wiring. `floorplan-pipeline`
feeds correct, schema-valid, spread mm coordinates through every seam; no change to
pipeline logic is warranted by this bug. Fix belongs in `aec-ifc-export`
(`walls.py` Defect A, `framing.py` Defect B), with the regression tests above added
there and a coordinate-spread assertion added to the pipeline's end-to-end test.
