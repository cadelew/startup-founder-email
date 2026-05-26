"""Shared pipeline orchestration utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from startup_founder_email.config import PipelineConfig, load_pipeline_config
from startup_founder_email.paths import ensure_output_directories_exist


@dataclass(frozen=True)
class PipelineContext:
    """Shared context passed into each pipeline stage."""

    project_root: Path
    config: PipelineConfig


def build_pipeline_context(project_root: Path) -> PipelineContext:
    """Load configuration and make sure the output layout exists."""

    pipeline_config = load_pipeline_config(project_root)
    return build_pipeline_context_from_config(project_root, pipeline_config)


def build_pipeline_context_from_config(
    project_root: Path,
    pipeline_config: PipelineConfig,
) -> PipelineContext:
    """Build a pipeline context from an existing configuration object."""

    ensure_output_directories_exist(pipeline_config.output_directories)
    return PipelineContext(project_root=project_root, config=pipeline_config)
