"""Collection stage entrypoint."""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import time
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
    """Collect page records from configured seed URLs using scrape or crawl mode."""

    if firecrawl_config.collection_mode == "crawl":
        return collect_live_firecrawl_crawl_records(
            firecrawl_config,
            request_timeout_seconds,
        )

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


def collect_live_firecrawl_crawl_records(
    firecrawl_config: FirecrawlConfig,
    request_timeout_seconds: float,
) -> list[FirecrawlPageRecord]:
    """Crawl each seed URL with Firecrawl and return one record per discovered page."""

    crawl_timeout_seconds = max(
        request_timeout_seconds,
        firecrawl_config.crawl_timeout_seconds,
    )
    firecrawl_page_records: list[FirecrawlPageRecord] = []
    for seed_url in firecrawl_config.target_urls:
        logger.info("Starting Firecrawl crawl for seed URL: %s", seed_url)
        firecrawl_page_records.extend(
            crawl_firecrawl_seed_url(
                firecrawl_config,
                seed_url,
                crawl_timeout_seconds,
            )
        )
    return firecrawl_page_records


def crawl_firecrawl_seed_url(
    firecrawl_config: FirecrawlConfig,
    seed_url: str,
    crawl_timeout_seconds: float,
) -> list[FirecrawlPageRecord]:
    """Run one Firecrawl crawl job for a seed URL and return page records."""

    crawl_response = post_firecrawl_crawl_request(
        firecrawl_config,
        seed_url,
        crawl_timeout_seconds,
    )
    crawl_id = read_string(crawl_response.get("id"))
    if not crawl_id:
        raise RuntimeError(f"Firecrawl crawl did not return an id: {crawl_response}")

    page_payloads = poll_firecrawl_crawl_until_complete(
        firecrawl_config,
        crawl_id,
        crawl_timeout_seconds,
    )
    fetched_at_iso = current_utc_timestamp()
    return crawl_results_to_page_records(
        seed_url=seed_url,
        crawl_id=crawl_id,
        page_payloads=page_payloads,
        fetched_at_iso=fetched_at_iso,
    )


def post_firecrawl_crawl_request(
    firecrawl_config: FirecrawlConfig,
    seed_url: str,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    """POST a crawl request to Firecrawl and return the decoded JSON response."""

    request_body = json.dumps(
        build_firecrawl_crawl_request_body(firecrawl_config, seed_url)
    ).encode("utf-8")
    return firecrawl_json_request(
        firecrawl_config,
        method="POST",
        path="/v1/crawl",
        request_body=request_body,
        request_timeout_seconds=request_timeout_seconds,
        error_context=f"Firecrawl crawl failed for {seed_url}",
    )


def poll_firecrawl_crawl_until_complete(
    firecrawl_config: FirecrawlConfig,
    crawl_id: str,
    crawl_timeout_seconds: float,
) -> list[dict[str, Any]]:
    """Poll a crawl job until it completes or times out."""

    deadline = time.monotonic() + crawl_timeout_seconds
    while time.monotonic() < deadline:
        status_response = get_firecrawl_crawl_status(
            firecrawl_config,
            crawl_id,
            min(firecrawl_config.crawl_poll_interval_seconds, crawl_timeout_seconds),
        )
        status = read_string(status_response.get("status")) or ""
        if status == "completed":
            return read_firecrawl_crawl_pages(status_response)
        if status == "failed":
            raise RuntimeError(f"Firecrawl crawl {crawl_id} failed: {status_response}")

        logger.info(
            "Firecrawl crawl %s status=%s completed=%s total=%s",
            crawl_id,
            status,
            status_response.get("completed"),
            status_response.get("total"),
        )
        time.sleep(firecrawl_config.crawl_poll_interval_seconds)

    raise RuntimeError(
        f"Firecrawl crawl {crawl_id} timed out after {crawl_timeout_seconds} seconds"
    )


def get_firecrawl_crawl_status(
    firecrawl_config: FirecrawlConfig,
    crawl_id: str,
    request_timeout_seconds: float,
) -> dict[str, Any]:
    """GET crawl job status from Firecrawl."""

    return firecrawl_json_request(
        firecrawl_config,
        method="GET",
        path=f"/v1/crawl/{crawl_id}",
        request_body=None,
        request_timeout_seconds=request_timeout_seconds,
        error_context=f"Firecrawl crawl status failed for {crawl_id}",
    )


def read_firecrawl_crawl_pages(status_response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract crawled page payloads from a completed crawl status response."""

    data = status_response.get("data")
    if isinstance(data, list):
        return [page for page in data if isinstance(page, dict)]
    return []


def crawl_results_to_page_records(
    *,
    seed_url: str,
    crawl_id: str,
    page_payloads: list[dict[str, Any]],
    fetched_at_iso: str,
) -> list[FirecrawlPageRecord]:
    """Convert Firecrawl crawl page payloads into pipeline page records."""

    page_records: list[FirecrawlPageRecord] = []
    for page_payload in page_payloads:
        page_payload = dict(page_payload)
        page_payload.setdefault("fetched_at_iso", fetched_at_iso)
        page_payload["seed_url"] = seed_url
        page_payload["crawl_id"] = crawl_id
        page_records.append(build_firecrawl_page_record(page_payload))
    return page_records


def build_firecrawl_crawl_request_body(
    firecrawl_config: FirecrawlConfig,
    seed_url: str,
) -> dict[str, Any]:
    """Build the JSON body for ``POST /v1/crawl``."""

    body: dict[str, Any] = {
        "url": seed_url,
        "limit": firecrawl_config.crawl_limit,
        "scrapeOptions": build_firecrawl_scrape_options(firecrawl_config),
    }
    if firecrawl_config.crawl_include_paths:
        body["includePaths"] = list(firecrawl_config.crawl_include_paths)
    if firecrawl_config.crawl_exclude_paths:
        body["excludePaths"] = list(firecrawl_config.crawl_exclude_paths)
    return body


def build_firecrawl_scrape_options(firecrawl_config: FirecrawlConfig) -> dict[str, Any]:
    """Build scrape options embedded in crawl requests."""

    scrape_options: dict[str, Any] = {
        "formats": ["markdown", "html", "links"],
    }
    if firecrawl_config.scrape_json_extract:
        scrape_options["formats"] = ["markdown", "html", "links", "json"]
        scrape_options["jsonOptions"] = {
            "schema": _FIRECRAWL_FOUNDER_JSON_SCHEMA,
            "prompt": _FIRECRAWL_FOUNDER_JSON_PROMPT,
        }
    return scrape_options


def firecrawl_json_request(
    firecrawl_config: FirecrawlConfig,
    *,
    method: str,
    path: str,
    request_body: bytes | None,
    request_timeout_seconds: float,
    error_context: str,
) -> dict[str, Any]:
    """Send a JSON request to Firecrawl and decode the response object."""

    request = urllib.request.Request(
        f"{firecrawl_config.base_url.rstrip('/')}{path}",
        data=request_body,
        headers=build_firecrawl_request_headers(firecrawl_config),
        method=method,
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
            f"{error_context}: HTTP {error.code} {response_body}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not connect to Firecrawl at {firecrawl_config.base_url}: {error.reason}"
        ) from error

    decoded_payload = json.loads(response_body)
    if not isinstance(decoded_payload, dict):
        raise RuntimeError("Firecrawl returned a non-object JSON response.")
    if decoded_payload.get("success") is False:
        raise RuntimeError(f"{error_context}: {decoded_payload}")
    return decoded_payload


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
        seed_url=read_optional_string(firecrawl_payload.get("seed_url")),
        crawl_id=read_optional_string(firecrawl_payload.get("crawl_id")),
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
