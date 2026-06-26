"""Pipeline configuration."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineConfig:
    wall_height_mm: float = 2438.0   # 8ft default storey height
    include_framing: bool = True     # framing on/off (the two demo cuts)
    include_sequence: bool = True    # produce assembly sequences
    include_ifc: bool = True         # export IFC4
    out_dir: str = "examples/out"
