"""Collection stage entrypoint."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from startup_founder_email.jsonl_io import write_jsonl_records
from startup_founder_email.models import FirecrawlPageRecord
from startup_founder_email.pipeline import PipelineContext

logger = logging.getLogger(__name__)


def run_collection_stage(context: PipelineContext) -> int:
    """Collect raw page records from the configured source."""

    firecrawl_page_records = collect_firecrawl_page_records(context)
    output_path = context.config.output_directories.raw_directory / "items.jsonl"
    write_jsonl_records(output_path, firecrawl_page_records)

    logger.info("Wrote %s raw page records to %s", len(firecrawl_page_records), output_path)
    return 0


def collect_firecrawl_page_records(context: PipelineContext) -> list[FirecrawlPageRecord]:
    """Collect page records using the configured Firecrawl mode."""

    if context.config.firecrawl.mode == "fixture":
        fixture_directory = context.config.output_directories.raw_directory / "_fixtures"
        return read_firecrawl_fixture_records(fixture_directory)

    raise NotImplementedError(
        "Live Firecrawl collection will be implemented after offline fixture mode."
    )


def read_firecrawl_fixture_records(fixture_directory: Path) -> list[FirecrawlPageRecord]:
    """Read Firecrawl-shaped fixture files from a directory."""

    fixture_paths = sorted(fixture_directory.glob("*.json"))
    if not fixture_paths:
        logger.warning("No Firecrawl fixture files found in %s", fixture_directory)
        return []

    return [
        build_firecrawl_page_record(read_json_file(fixture_path))
        for fixture_path in fixture_paths
    ]


def read_json_file(json_path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""

    with json_path.open(encoding="utf-8") as json_file:
        return json.load(json_file)


def build_firecrawl_page_record(firecrawl_payload: dict[str, Any]) -> FirecrawlPageRecord:
    """Convert one Firecrawl-shaped payload into the pipeline's raw page record."""

    metadata = read_mapping(firecrawl_payload.get("metadata"))
    links = tuple(read_string_items(firecrawl_payload.get("links")))

    return FirecrawlPageRecord(
        url=read_string(firecrawl_payload.get("url"))
        or read_string(metadata.get("sourceURL"))
        or read_string(metadata.get("url"))
        or "",
        fetched_at_iso=read_string(firecrawl_payload.get("fetched_at_iso")) or "",
        status_code=read_status_code(firecrawl_payload.get("statusCode")),
        markdown=read_optional_string(firecrawl_payload.get("markdown")),
        html=read_optional_string(firecrawl_payload.get("html")),
        links=links,
        metadata=metadata,
    )


def read_mapping(value: object) -> dict[str, Any]:
    """Return a dictionary value or an empty dictionary."""

    if isinstance(value, dict):
        return value
    return {}


def read_string_items(value: object) -> Iterable[str]:
    """Return string items from a JSON list."""

    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def read_string(value: object) -> str | None:
    """Return a non-empty string value."""

    if isinstance(value, str) and value:
        return value
    return None


def read_optional_string(value: object) -> str | None:
    """Return a string value while preserving missing values."""

    if isinstance(value, str):
        return value
    return None


def read_status_code(value: object) -> int | None:
    """Return an integer HTTP status code when present."""

    if isinstance(value, int):
        return value
    return None
