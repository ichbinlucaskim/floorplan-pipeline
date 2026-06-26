# 30-Second Demo Video — Storyboard

Record two versions by toggling `PipelineConfig(include_framing=...)`:
- **Full framing** (Promise Robotics audience) — the headline cut.
- **Walls-only** (Augmenta / Forma / Arcol audience) — interoperability cut.

Generate the artifacts first: `make demo` (writes `examples/out/`), and have the
component viz images handy (`wall-extract`, `panel-decompose`, `framing-synth`,
`assembly-sequence` each produce a `demo_viz.png`).

## Three cuts

```
0:00–0:05  HOOK — the input.
           A room-plan polygon appears (examples/input_rooms.json rendered, or a
           ResPlan plan). Caption: "Start: a floor-plan polygon."

0:05–0:12  COMMON CUT — extract + decompose.
           Fast montage: wall-extract's 2D viz (red = exterior, blue = interior),
           then panel-decompose's panels (colour = parent wall, | = split).
           Caption: "Walls extracted → split into transport panels."

0:12–0:22  FRAMING CUT (Promise) — synthesise + sequence.
           framing-synth elevation fills with plates/studs/header/sill/cripples;
           cut to assembly-sequence's numbered build-up (members 1 → N, viridis
           ramp). Caption: "Framing synthesised → ordered for fabrication."

0:22–0:30  IFC CUT — interoperate.
           Open examples/out/model.ifc in Open IFC Viewer. Orbit the 3D framing;
           expand the tree Wall → Panel → Member. End on the full framing.
           Caption: "Exported to IFC4 — opens in any BIM viewer. No Revit."
```

## Notes

- **Two versions:** re-render the IFC cut with `include_framing=False` for the
  walls-only audience (lighter model, faster orbit).
- **GIF export (README / LinkedIn):** screen-record at 1280×720, then
  `ffmpeg -i demo.mov -vf "fps=12,scale=900:-1" -loop 0 demo.gif` (keep < 8 MB).
  Drop the GIF at the top of `README.md` where the `[30s demo GIF here]` marker is.
- Keep each caption to one line; let the visuals carry it.
