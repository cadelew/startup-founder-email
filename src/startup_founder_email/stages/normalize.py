"""Normalization stage entrypoint."""

from __future__ import annotations

import logging
import re
from typing import Any

from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import FirecrawlPageRecord, NormalizedFounderRecord
from startup_founder_email.pipeline import PipelineContext
from startup_founder_email.text_normalization import normalize_visible_text

logger = logging.getLogger(__name__)


def run_normalization_stage(context: PipelineContext) -> int:
    """Normalize raw pages into founder records."""

    raw_page_records = read_raw_page_records(context)
    normalized_founder_records = normalize_raw_page_records(raw_page_records)
    output_path = context.config.output_directories.normalized_directory / "items.jsonl"
    write_jsonl_records(output_path, normalized_founder_records)

    logger.info(
        "Wrote %s normalized founder records to %s",
        len(normalized_founder_records),
        output_path,
    )
    return 0


def read_raw_page_records(context: PipelineContext) -> list[FirecrawlPageRecord]:
    """Read collected page records from raw JSONL."""

    input_path = context.config.output_directories.raw_directory / "items.jsonl"
    return [
        FirecrawlPageRecord(
            url=str(record.get("url", "")),
            fetched_at_iso=str(record.get("fetched_at_iso", "")),
            status_code=read_optional_integer(record.get("status_code")),
            markdown=read_optional_string(record.get("markdown")),
            html=read_optional_string(record.get("html")),
            links=tuple(read_string_items(record.get("links"))),
            metadata=read_mapping(record.get("metadata")),
        )
        for record in iter_jsonl_records(input_path)
    ]


def normalize_raw_page_records(
    raw_page_records: list[FirecrawlPageRecord],
) -> list[NormalizedFounderRecord]:
    """Convert raw page records into normalized founder rows."""

    normalized_founder_records: list[NormalizedFounderRecord] = []
    for raw_page_record in raw_page_records:
        normalized_founder_records.extend(normalize_raw_page_record(raw_page_record))
    return normalized_founder_records


def normalize_raw_page_record(
    raw_page_record: FirecrawlPageRecord,
) -> list[NormalizedFounderRecord]:
    """Normalize one raw page record into one or more founder rows."""

    page_text = raw_page_record.markdown or raw_page_record.html or ""
    company_name = extract_company_name(page_text, raw_page_record)
    founder_segments = extract_founder_segments(page_text)
    public_email_address = extract_public_email_address(page_text, raw_page_record.links)
    public_email_source_type = classify_public_email_source_type(public_email_address)
    company_description = extract_company_description(page_text, company_name)

    if not founder_segments:
        return [
            build_unknown_founder_record(
                raw_page_record,
                company_name,
                company_description,
                public_email_address,
                public_email_source_type,
            )
        ]

    return [
        build_founder_record(
            raw_page_record,
            company_name,
            company_description,
            public_email_address,
            public_email_source_type,
            founder_segment,
        )
        for founder_segment in founder_segments
    ]


def build_founder_record(
    raw_page_record: FirecrawlPageRecord,
    company_name: str,
    company_description: str | None,
    public_email_address: str | None,
    public_email_source_type: str,
    founder_segment: str,
) -> NormalizedFounderRecord:
    """Build one normalized founder record from a founder segment."""

    founder_name, founder_role_title = split_founder_name_and_role(founder_segment)
    founder_first_name, founder_last_name = split_person_name(founder_name)
    return NormalizedFounderRecord(
        company_name=company_name,
        batch_name=None,
        industry_name=None,
        company_website_url=raw_page_record.url,
        raw_company_description=company_description,
        founder_full_name=founder_name,
        founder_first_name=founder_first_name,
        founder_last_name=founder_last_name,
        founder_role_title=founder_role_title,
        founder_linkedin_url=None,
        source_url=raw_page_record.url,
        public_email_address=public_email_address,
        public_email_source_type=public_email_source_type,
    )


def build_unknown_founder_record(
    raw_page_record: FirecrawlPageRecord,
    company_name: str,
    company_description: str | None,
    public_email_address: str | None,
    public_email_source_type: str,
) -> NormalizedFounderRecord:
    """Build a placeholder record when page text does not list founders."""

    return NormalizedFounderRecord(
        company_name=company_name,
        batch_name=None,
        industry_name=None,
        company_website_url=raw_page_record.url,
        raw_company_description=company_description,
        founder_full_name="",
        founder_first_name=None,
        founder_last_name=None,
        founder_role_title=None,
        founder_linkedin_url=None,
        source_url=raw_page_record.url,
        public_email_address=public_email_address,
        public_email_source_type=public_email_source_type,
        cleaning_notes=("founder_not_found",),
    )


def extract_company_name(page_text: str, raw_page_record: FirecrawlPageRecord) -> str:
    """Extract the company name from heading text or metadata."""

    for line in page_text.splitlines():
        cleaned_line = line.strip()
        if cleaned_line.startswith("#"):
            heading_text = cleaned_line.lstrip("#").strip()
            if heading_text:
                return heading_text

    title = raw_page_record.metadata.get("title")
    if isinstance(title, str) and title:
        return title
    return raw_page_record.url


def extract_company_description(page_text: str, company_name: str) -> str | None:
    """Extract the first useful paragraph as a company description."""

    for paragraph in page_text.split("\n\n"):
        cleaned_paragraph = normalize_visible_text(paragraph)
        if not cleaned_paragraph or cleaned_paragraph.startswith("#"):
            continue
        if cleaned_paragraph.startswith("Founders:") or cleaned_paragraph.startswith("Contact:"):
            continue
        if cleaned_paragraph.startswith("Website:"):
            continue
        if cleaned_paragraph == company_name:
            continue
        return cleaned_paragraph
    return None


def extract_founder_segments(page_text: str) -> list[str]:
    """Extract founder name and role segments from page text."""

    founder_line = extract_labeled_line(page_text, "Founders")
    if not founder_line:
        return []

    return [
        segment.strip()
        for segment in re.split(r"\s+and\s+", founder_line)
        if segment.strip()
    ]


def extract_labeled_line(page_text: str, label: str) -> str | None:
    """Extract the text after a simple markdown-style label."""

    pattern = re.compile(rf"^{re.escape(label)}:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(page_text)
    if not match:
        return None
    return normalize_visible_text(match.group(1))


def extract_public_email_address(
    page_text: str,
    links: tuple[str, ...],
) -> str | None:
    """Extract the first public email address from text or mailto links."""

    for link in links:
        if link.lower().startswith("mailto:"):
            email_address = link.split(":", 1)[1].split("?", 1)[0]
            if email_address:
                return email_address

    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", page_text)
    if email_match:
        return email_match.group(0)
    return None


def classify_public_email_source_type(public_email_address: str | None) -> str:
    """Classify extracted page email as company-level unless proven otherwise."""

    if public_email_address:
        return "company"
    return ""


def split_founder_name_and_role(founder_segment: str) -> tuple[str, str | None]:
    """Split a founder segment into name and optional role title."""

    name_part, separator, role_part = founder_segment.partition(",")
    founder_name = normalize_visible_text(name_part)
    founder_role_title = normalize_visible_text(role_part) if separator else None
    return founder_name, founder_role_title or None


def split_person_name(person_name: str) -> tuple[str | None, str | None]:
    """Split a full person name into first and last name."""

    name_parts = person_name.split()
    if not name_parts:
        return None, None
    if len(name_parts) == 1:
        return name_parts[0], None
    return name_parts[0], name_parts[-1]


def read_optional_integer(value: object) -> int | None:
    """Return an integer value when present."""

    if isinstance(value, int):
        return value
    return None


def read_optional_string(value: object) -> str | None:
    """Return a string value while preserving missing values."""

    if isinstance(value, str):
        return value
    return None


def read_string_items(value: object) -> list[str]:
    """Return string values from a JSON array."""

    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def read_mapping(value: object) -> dict[str, Any]:
    """Return a dictionary value or an empty dictionary."""

    if isinstance(value, dict):
        return value
    return {}
