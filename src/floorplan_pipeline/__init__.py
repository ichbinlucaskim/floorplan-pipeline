"""
floorplan-pipeline — end-to-end orchestrator for the AEC framing pipeline.

Composes five independent processing repos (wall-extract, panel-decompose,
framing-synth, assembly-sequence, aec-ifc-export) over aec-schema contracts.
Thin by design: all domain logic lives in the components; this repo wires the
stages together and verifies the seams.

Usage
-----
    from floorplan_pipeline import run_pipeline, PipelineConfig
    summary = run_pipeline(rooms, PipelineConfig(include_framing=True))
"""
from __future__ import annotations

from .config import PipelineConfig
from .pipeline import IfcValidation, run_pipeline, validate_ifc
from .resplan_input import (
    load_resplan_plan,
    plan_id_str,
    record_to_rooms,
    run_pipeline_for_plan,
)

__all__ = [
    "run_pipeline",
    "run_pipeline_for_plan",
    "PipelineConfig",
    "load_resplan_plan",
    "record_to_rooms",
    "plan_id_str",
    "validate_ifc",
    "IfcValidation",
]
__version__ = "0.1.0"
