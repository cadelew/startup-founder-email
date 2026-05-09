"""Command-line interface for the founder outreach pipeline."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable

from startup_founder_email.logging_utils import configure_logging
from startup_founder_email.pipeline import PipelineContext, build_pipeline_context
from startup_founder_email.stages.collect import run_collection_stage
from startup_founder_email.stages.enrich import run_enrichment_stage
from startup_founder_email.stages.export import run_export_stage
from startup_founder_email.stages.generate import run_contact_generation_stage
from startup_founder_email.stages.normalize import run_normalization_stage
from startup_founder_email.stages.validate import run_validation_stage

logger = logging.getLogger(__name__)

StageRunner = Callable[[PipelineContext], int]


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the top-level command-line parser."""

    argument_parser = argparse.ArgumentParser(
        prog="startup-founder-email",
        description="A readable founder outreach data pipeline.",
    )
    argument_parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the project root. Defaults to the current working directory.",
    )

    subparsers = argument_parser.add_subparsers(dest="stage_name", required=True)

    _add_stage_parser(
        subparsers=subparsers,
        stage_name="collect",
        help_text="Collect raw company data from the source.",
    )
    _add_stage_parser(
        subparsers=subparsers,
        stage_name="normalize",
        help_text="Normalize raw company data into founder rows.",
    )
    _add_stage_parser(
        subparsers=subparsers,
        stage_name="enrich",
        help_text="Add domain and MX metadata.",
    )
    _add_stage_parser(
        subparsers=subparsers,
        stage_name="generate",
        help_text="Generate public or inferred contact candidates.",
    )
    _add_stage_parser(
        subparsers=subparsers,
        stage_name="validate",
        help_text="Validate generated contact candidates.",
    )
    _add_stage_parser(
        subparsers=subparsers,
        stage_name="export",
        help_text="Export the final outreach CSV.",
    )

    return argument_parser


def _add_stage_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    stage_name: str,
    help_text: str,
) -> None:
    """Register a single pipeline stage with the parser."""

    stage_parser = subparsers.add_parser(stage_name, help=help_text)
    stage_parser.set_defaults(stage_name=stage_name)


def determine_stage_runner(stage_name: str) -> StageRunner:
    """Map a CLI stage name to its implementation."""

    stage_runners: dict[str, StageRunner] = {
        "collect": run_collection_stage,
        "normalize": run_normalization_stage,
        "enrich": run_enrichment_stage,
        "generate": run_contact_generation_stage,
        "validate": run_validation_stage,
        "export": run_export_stage,
    }

    return stage_runners[stage_name]


def main(argv: list[str] | None = None) -> int:
    """Run the command-line entrypoint."""

    configure_logging()
    argument_parser = build_argument_parser()
    parsed_arguments = argument_parser.parse_args(argv)

    pipeline_context = build_pipeline_context(parsed_arguments.project_root.resolve())
    stage_runner = determine_stage_runner(parsed_arguments.stage_name)

    logger.info("Starting stage: %s", parsed_arguments.stage_name)
    logger.info(
        "Pipeline directories are rooted at: %s",
        pipeline_context.config.output_directories.project_root,
    )

    try:
        return stage_runner(pipeline_context)
    except NotImplementedError as error:
        logger.error("%s", error)
        return 1
