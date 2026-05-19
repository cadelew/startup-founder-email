"""Collection stage entrypoint."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from startup_founder_email.config import FirecrawlConfig
from startup_founder_email.jsonl_io import write_jsonl_records
from startup_founder_email.models import FirecrawlPageRecord
from startup_founder_email.pipeline import PipelineContext

logger = logging.getLogger(__name__)

# JSON Schema for Firecrawl ``formats: ["json"]`` + ``jsonOptions`` (uses host LLM when configured).
_FIRECRAWL_FOUNDER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "company_name": {
            "type": "string",
            "description": "Public or legal company name shown on the page",
        },
        "company_description": {
            "type": "string",
            "description": "One short paragraph: what the company does",
        },
        "founders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string"},
                    "role_title": {"type": "string"},
                    "email": {"type": "string"},
                    "linkedin_url": {"type": "string"},
                },
                "required": ["full_name"],
            },
        },
    },
    "required": ["founders"],
}

_FIRECRAWL_FOUNDER_JSON_PROMPT = (
    "Extract the company name, a short company description, and every founder or co-founder "
    "mentioned on this page. Include their titles, any public email addresses, and LinkedIn "
    "profile URLs if clearly associated with that person."
)
_FOUNDER_LABEL_LINE = re.compile(r"^Founders:\s*.+$", re.IGNORECASE | re.MULTILINE)
_FOUNDER_ROLE_LINE = re.compile(r"^\s*(Co-)?Founder\s*,\s*\S", re.IGNORECASE | re.MULTILINE)
_MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\([^)]*\)")
_MIN_MARKDOWN_LENGTH_BEFORE_LLM_FALLBACK = 250


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

    if context.config.firecrawl.mode == "live":
        return collect_live_firecrawl_page_records(
            context.config.firecrawl,
            context.config.request_timing.request_timeout_seconds,
        )

    raise NotImplementedError(f"Unsupported Firecrawl mode: {context.config.firecrawl.mode}")


def collect_live_firecrawl_page_records(
    firecrawl_config: FirecrawlConfig,
    request_timeout_seconds: float,
) -> list[FirecrawlPageRecord]:
    """Collect page records by scraping configured target URLs with Firecrawl."""

    scrape_timeout_seconds = resolve_firecrawl_scrape_timeout_seconds(
        firecrawl_config,
        request_timeout_seconds,
    )
    return [
        scrape_firecrawl_page_record(
            firecrawl_config,
            target_url,
            scrape_timeout_seconds,
        )
        for target_url in firecrawl_config.target_urls
    ]


def resolve_firecrawl_scrape_timeout_seconds(
    firecrawl_config: FirecrawlConfig,
    base_timeout_seconds: float,
) -> float:
    """Allow longer waits when Firecrawl may run an on-host LLM for JSON extraction."""

    if not firecrawl_config.scrape_json_extract:
        return base_timeout_seconds
    if firecrawl_config.llm_timeout_seconds is not None:
        return firecrawl_config.llm_timeout_seconds
    return max(base_timeout_seconds, 90.0)


def scrape_firecrawl_page_record(
    firecrawl_config: FirecrawlConfig,
    target_url: str,
    request_timeout_seconds: float,
) -> FirecrawlPageRecord:
    """Scrape one URL through Firecrawl's synchronous scrape endpoint."""

    response_payload = post_firecrawl_scrape_request(
        firecrawl_config,
        target_url,
        request_timeout_seconds,
        include_json_extract=False,
    )
    firecrawl_payload = read_firecrawl_data_payload(response_payload)

    if firecrawl_config.scrape_json_extract:
        should_request_json, fallback_reasons = should_request_llm_extraction(firecrawl_payload)
        if should_request_json:
            logger.info(
                "Requesting Firecrawl JSON extraction for %s because: %s",
                target_url,
                ", ".join(fallback_reasons),
            )
            json_response_payload = post_firecrawl_scrape_request(
                firecrawl_config,
                target_url,
                request_timeout_seconds,
                include_json_extract=True,
            )
            json_firecrawl_payload = read_firecrawl_data_payload(json_response_payload)
            merge_firecrawl_json_extraction_payload(firecrawl_payload, json_firecrawl_payload)

    firecrawl_payload.setdefault("url", target_url)
    firecrawl_payload.setdefault("fetched_at_iso", current_utc_timestamp())
    return build_firecrawl_page_record(firecrawl_payload)


def post_firecrawl_scrape_request(
    firecrawl_config: FirecrawlConfig,
    target_url: str,
    request_timeout_seconds: float,
    *,
    include_json_extract: bool | None = None,
) -> dict[str, Any]:
    """POST a scrape request to Firecrawl and return the decoded JSON response."""

    request_body = json.dumps(
        build_firecrawl_scrape_request_body(
            firecrawl_config,
            target_url,
            include_json_extract=include_json_extract,
        )
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{firecrawl_config.base_url.rstrip('/')}/v1/scrape",
        data=request_body,
        headers=build_firecrawl_request_headers(firecrawl_config),
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=request_timeout_seconds,
        ) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Firecrawl scrape failed for {target_url}: HTTP {error.code} {response_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not connect to Firecrawl at {firecrawl_config.base_url}: {error.reason}"
        ) from error

    decoded_payload = json.loads(response_body)
    if not isinstance(decoded_payload, dict):
        raise RuntimeError("Firecrawl returned a non-object JSON response.")
    return decoded_payload


def build_firecrawl_scrape_request_body(
    firecrawl_config: FirecrawlConfig,
    target_url: str,
    *,
    include_json_extract: bool | None = None,
) -> dict[str, Any]:
    """Build the JSON body for ``POST /v1/scrape``."""

    should_include_json = (
        firecrawl_config.scrape_json_extract
        if include_json_extract is None
        else include_json_extract
    )
    body: dict[str, Any] = {
        "url": target_url,
        "formats": ["markdown", "html", "links"],
    }
    if should_include_json:
        body["formats"] = ["markdown", "html", "links", "json"]
        body["jsonOptions"] = {
            "schema": _FIRECRAWL_FOUNDER_JSON_SCHEMA,
            "prompt": _FIRECRAWL_FOUNDER_JSON_PROMPT,
        }
    return body


def should_request_llm_extraction(
    firecrawl_payload: dict[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    """Return whether a scraped page needs an LLM fallback and why."""

    markdown = read_optional_string(firecrawl_payload.get("markdown")) or ""
    html = read_optional_string(firecrawl_payload.get("html")) or ""
    page_text = markdown or html
    reasons: list[str] = []
    has_founder_signal = page_text_has_founder_signal(page_text)

    if not page_text.strip():
        reasons.append("empty_page_text")
    if (
        not has_founder_signal
        and markdown
        and len(markdown) < _MIN_MARKDOWN_LENGTH_BEFORE_LLM_FALLBACK
    ):
        reasons.append("short_markdown")
    if markdown_looks_nav_heavy(markdown):
        reasons.append("nav_heavy_markdown")
    if not has_founder_signal:
        reasons.append("founder_signal_not_found")

    return bool(reasons), tuple(reasons)


def page_text_has_founder_signal(page_text: str) -> bool:
    """Detect founder patterns already handled by deterministic normalization."""

    return bool(_FOUNDER_LABEL_LINE.search(page_text) or _FOUNDER_ROLE_LINE.search(page_text))


def markdown_looks_nav_heavy(markdown: str) -> bool:
    """Detect markdown that is mostly links/navigation instead of useful prose."""

    if not markdown.strip():
        return False

    normalized_markdown = markdown.strip()
    link_text_length = sum(len(match.group(0)) for match in _MARKDOWN_LINK.finditer(normalized_markdown))
    if link_text_length == 0:
        return False

    link_ratio = link_text_length / max(len(normalized_markdown), 1)
    prose_lines = [
        line.strip()
        for line in normalized_markdown.splitlines()
        if line.strip()
        and not line.strip().startswith("[")
        and not line.strip().startswith("![")
        and len(line.strip()) >= 40
    ]
    return link_ratio > 0.35 and len(prose_lines) <= 1


def merge_firecrawl_json_extraction_payload(
    base_payload: dict[str, Any],
    json_payload: dict[str, Any],
) -> None:
    """Copy structured LLM extraction fields into an existing scrape payload."""

    for key in ("json", "llm_extraction", "warning"):
        if key in json_payload:
            base_payload[key] = json_payload[key]


def build_firecrawl_request_headers(firecrawl_config: FirecrawlConfig) -> dict[str, str]:
    """Build headers for a Firecrawl JSON request."""

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    api_key = os.environ.get(firecrawl_config.api_key_environment_variable)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def read_firecrawl_data_payload(response_payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the Firecrawl data object from a scrape response."""

    if response_payload.get("success") is False:
        raise RuntimeError(f"Firecrawl scrape failed: {response_payload}")

    data_payload = response_payload.get("data")
    if not isinstance(data_payload, dict):
        raise RuntimeError(f"Firecrawl response did not include a data object: {response_payload}")
    return data_payload


def current_utc_timestamp() -> str:
    """Return a compact UTC timestamp for live collection records."""

    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        status_code=read_status_code(firecrawl_payload.get("statusCode"))
        or read_status_code(metadata.get("statusCode")),
        markdown=read_optional_string(firecrawl_payload.get("markdown")),
        html=read_optional_string(firecrawl_payload.get("html")),
        links=links,
        metadata=metadata,
        llm_extraction=read_llm_extraction_payload(firecrawl_payload),
    )


def read_llm_extraction_payload(firecrawl_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Read structured LLM output from a scrape ``data`` object."""

    llm_raw = firecrawl_payload.get("llm_extraction")
    if isinstance(llm_raw, dict):
        return llm_raw
    json_raw = firecrawl_payload.get("json")
    if isinstance(json_raw, dict):
        return json_raw
    return None


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
