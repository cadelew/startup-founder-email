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

# Lines like "Founder, CEO" or "Co-Founder, CTO" on /team-style pages (name on the previous text line).
_FOUNDER_ROLE_LINE = re.compile(r"^\s*(Co-)?Founder\s*,\s*\S", re.IGNORECASE)
_MARKDOWN_LINK_ONLY_LINE = re.compile(r"^\[[^\]]+\]\([^)]*\)\s*$")
_UNDERLINE_HEADING_LINE = re.compile(r"^\s*-+\s*$")
_MARKDOWN_INLINE_LINK = re.compile(r"\[[^\]]+\]\([^)]*\)")
_GENERIC_MARKDOWN_HEADINGS = frozenset(
    {
        "about",
        "about us",
        "blog",
        "careers",
        "contact",
        "leadership",
        "meet the team",
        "our team",
        "team",
    }
)
_FOUNDER_SECTION_HEADINGS = frozenset(
    {
        "leadership",
        "meet the team",
        "our founders",
        "the team",
    }
)
_MIN_DESCRIPTION_CHARS = 30


def run_normalization_stage(context: PipelineContext) -> int:
    """Normalize raw pages into founder records."""

    raw_page_records = read_raw_page_records(context)
    normalized_founder_records = dedupe_normalized_founders(
        normalize_raw_page_records(raw_page_records)
    )
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
            llm_extraction=read_optional_mapping(record.get("llm_extraction")),
            seed_url=read_optional_string(record.get("seed_url")),
            crawl_id=read_optional_string(record.get("crawl_id")),
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


def dedupe_normalized_founders(
    normalized_founder_records: list[NormalizedFounderRecord],
) -> list[NormalizedFounderRecord]:
    """Keep one founder row per company group, preferring the richest source page."""

    best_by_key: dict[tuple[str, str], NormalizedFounderRecord] = {}
    for founder_record in normalized_founder_records:
        if not founder_record.founder_full_name.strip():
            continue
        dedupe_key = build_founder_dedupe_key(founder_record)
        existing_record = best_by_key.get(dedupe_key)
        if existing_record is None or founder_record_rank(
            founder_record
        ) > founder_record_rank(existing_record):
            best_by_key[dedupe_key] = founder_record
    return list(best_by_key.values())


def build_founder_dedupe_key(founder_record: NormalizedFounderRecord) -> tuple[str, str]:
    """Build a stable deduplication key for one founder within one startup."""

    company_key = (
        founder_record.seed_url
        or founder_record.company_website_url
        or founder_record.company_name
    ).strip().lower()
    founder_name_key = founder_record.founder_full_name.strip().lower()
    return company_key, founder_name_key


def founder_record_rank(founder_record: NormalizedFounderRecord) -> int:
    """Score founder rows so dedupe keeps the most useful source page."""

    score = 0
    if founder_record.public_email_address:
        score += 100
    if "founder_source_firecrawl_json" in founder_record.cleaning_notes:
        score += 50
    if page_path_looks_founder_relevant(founder_record.source_url):
        score += 30
    if founder_record.raw_company_description:
        score += min(len(founder_record.raw_company_description), 200)
    return score


def page_path_looks_founder_relevant(page_url: str) -> bool:
    """Return whether a page URL path likely contains team or about content."""

    lowered_url = page_url.lower()
    founder_path_markers = (
        "/team",
        "/about",
        "/leadership",
        "/people",
        "/founders",
        "/company",
    )
    return any(marker in lowered_url for marker in founder_path_markers)


def resolve_company_website_url(raw_page_record: FirecrawlPageRecord) -> str | None:
    """Prefer the crawl seed URL as the company website when available."""

    return raw_page_record.seed_url or raw_page_record.url


def normalize_raw_page_record(
    raw_page_record: FirecrawlPageRecord,
) -> list[NormalizedFounderRecord]:
    """Normalize one raw page record into one or more founder rows."""

    page_text = raw_page_record.markdown or raw_page_record.html or ""
    llm_founder_entries = read_firecrawl_json_founder_entries(raw_page_record.llm_extraction)
    if llm_founder_entries:
        return normalize_raw_page_record_from_firecrawl_json(
            raw_page_record,
            page_text,
            llm_founder_entries,
        )

    company_name = extract_company_name(page_text, raw_page_record)
    founder_segments = extract_founder_segments(page_text)
    public_email_address = extract_public_email_address(page_text, raw_page_record.links)
    public_email_source_type = classify_public_email_source_type(public_email_address)
    company_description = extract_company_description(
        page_text, company_name, raw_page_record.metadata
    )

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


def read_firecrawl_json_founder_entries(
    llm_extraction: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return founder objects from Firecrawl JSON / LLM scrape output."""

    if not isinstance(llm_extraction, dict):
        return []
    founders_raw = llm_extraction.get("founders")
    if not isinstance(founders_raw, list):
        return []
    return [
        item
        for item in founders_raw
        if isinstance(item, dict) and str(item.get("full_name", "")).strip()
    ]


def normalize_raw_page_record_from_firecrawl_json(
    raw_page_record: FirecrawlPageRecord,
    page_text: str,
    llm_founder_entries: list[dict[str, Any]],
) -> list[NormalizedFounderRecord]:
    """Prefer structured founders from Firecrawl ``json`` / ``llm_extraction`` when present."""

    extraction_payload = raw_page_record.llm_extraction or {}

    heuristic_company_name = extract_company_name(page_text, raw_page_record)
    heuristic_description = extract_company_description(
        page_text, heuristic_company_name, raw_page_record.metadata
    )
    company_name, company_description = merge_company_fields_from_firecrawl_json(
        extraction_payload,
        heuristic_company_name,
        heuristic_description,
    )
    page_public_email = extract_public_email_address(page_text, raw_page_record.links)
    page_public_email_type = classify_public_email_source_type(page_public_email)

    normalized_records: list[NormalizedFounderRecord] = []
    for founder_entry in llm_founder_entries:
        founder_segment = format_founder_segment_from_firecrawl_json_entry(founder_entry)
        founder_email = read_optional_trimmed_string(founder_entry.get("email"))
        founder_linkedin_url = read_optional_trimmed_string(founder_entry.get("linkedin_url"))
        if founder_email:
            row_public_email = founder_email
            row_public_email_type = "person"
        else:
            row_public_email = page_public_email
            row_public_email_type = page_public_email_type

        normalized_records.append(
            build_founder_record(
                raw_page_record,
                company_name,
                company_description,
                row_public_email,
                row_public_email_type,
                founder_segment,
                founder_linkedin_url=founder_linkedin_url,
                cleaning_notes=("founder_source_firecrawl_json",),
            )
        )
    return normalized_records


def merge_company_fields_from_firecrawl_json(
    llm_extraction: dict[str, Any],
    heuristic_company_name: str,
    heuristic_description: str | None,
) -> tuple[str, str | None]:
    """Let non-empty JSON extraction override heuristic company fields."""

    company_name = heuristic_company_name
    company_description = heuristic_description
    extracted_name = llm_extraction.get("company_name")
    if isinstance(extracted_name, str) and extracted_name.strip():
        normalized_extracted_name = normalize_visible_text(extracted_name)
        if not is_less_specific_company_name(
            normalized_extracted_name,
            heuristic_company_name,
        ):
            company_name = normalized_extracted_name
    extracted_description = llm_extraction.get("company_description")
    if isinstance(extracted_description, str) and extracted_description.strip():
        company_description = normalize_visible_text(extracted_description)
    return company_name, company_description


def is_less_specific_company_name(candidate_name: str, fallback_name: str) -> bool:
    """Return True when the extracted name is just a shorter slice of metadata."""

    normalized_candidate = candidate_name.lower()
    normalized_fallback = fallback_name.lower()
    return (
        normalized_candidate != normalized_fallback
        and normalized_candidate in normalized_fallback
        and len(normalized_candidate) < len(normalized_fallback)
    )


def format_founder_segment_from_firecrawl_json_entry(founder_entry: dict[str, Any]) -> str:
    """Build a ``Name, Role`` segment compatible with ``split_founder_name_and_role``."""

    founder_name = normalize_visible_text(str(founder_entry.get("full_name", "")))
    role_title = founder_entry.get("role_title")
    if isinstance(role_title, str) and role_title.strip():
        return f"{founder_name}, {normalize_visible_text(role_title)}"
    return founder_name


def build_founder_record(
    raw_page_record: FirecrawlPageRecord,
    company_name: str,
    company_description: str | None,
    public_email_address: str | None,
    public_email_source_type: str,
    founder_segment: str,
    *,
    founder_linkedin_url: str | None = None,
    cleaning_notes: tuple[str, ...] = (),
) -> NormalizedFounderRecord:
    """Build one normalized founder record from a founder segment."""

    founder_name, founder_role_title = split_founder_name_and_role(founder_segment)
    founder_first_name, founder_last_name = split_person_name(founder_name)
    return NormalizedFounderRecord(
        company_name=company_name,
        batch_name=None,
        industry_name=None,
        company_website_url=resolve_company_website_url(raw_page_record),
        raw_company_description=company_description,
        founder_full_name=founder_name,
        founder_first_name=founder_first_name,
        founder_last_name=founder_last_name,
        founder_role_title=founder_role_title,
        founder_linkedin_url=founder_linkedin_url,
        source_url=raw_page_record.url,
        seed_url=raw_page_record.seed_url,
        public_email_address=public_email_address,
        public_email_source_type=public_email_source_type,
        cleaning_notes=cleaning_notes,
    )


def read_optional_trimmed_string(value: object) -> str | None:
    """Return a non-empty stripped string or None."""

    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return None


def read_optional_mapping(value: object) -> dict[str, Any] | None:
    """Return a mapping for optional JSON object fields."""

    if isinstance(value, dict):
        return value
    return None


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
        company_website_url=resolve_company_website_url(raw_page_record),
        raw_company_description=company_description,
        founder_full_name="",
        founder_first_name=None,
        founder_last_name=None,
        founder_role_title=None,
        founder_linkedin_url=None,
        source_url=raw_page_record.url,
        seed_url=raw_page_record.seed_url,
        public_email_address=public_email_address,
        public_email_source_type=public_email_source_type,
        cleaning_notes=("founder_not_found",),
    )


def extract_company_name(page_text: str, raw_page_record: FirecrawlPageRecord) -> str:
    """Extract the company name from heading text or metadata."""

    metadata = raw_page_record.metadata
    site_name = read_metadata_string(metadata, ("og:site_name", "ogSiteName", "site_name"))
    if site_name:
        return site_name

    for line in page_text.splitlines():
        cleaned_line = line.strip()
        if cleaned_line.startswith("#"):
            heading_text = cleaned_line.lstrip("#").strip()
            if heading_text:
                normalized_heading = normalize_visible_text(heading_text).lower()
                if normalized_heading not in _GENERIC_MARKDOWN_HEADINGS:
                    return normalize_visible_text(heading_text)

    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        stripped_title = title.strip()
        if " - " in stripped_title:
            suffix = stripped_title.rsplit(" - ", 1)[-1].strip()
            if suffix:
                return normalize_visible_text(suffix)
        return normalize_visible_text(stripped_title)

    return raw_page_record.url


def extract_company_description(
    page_text: str, company_name: str, metadata: dict[str, Any]
) -> str | None:
    """Extract the first useful paragraph as a company description."""

    section_blurb = extract_blurb_after_team_section_heading(page_text)
    if section_blurb:
        return section_blurb

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
        if len(cleaned_paragraph) < _MIN_DESCRIPTION_CHARS:
            continue
        if paragraph_looks_like_markdown_breadcrumb(paragraph):
            continue
        return cleaned_paragraph

    meta_description = read_metadata_string(
        metadata, ("og:description", "ogDescription", "description")
    )
    return meta_description


def read_metadata_string(metadata: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty string among common metadata keys."""

    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            cleaned = normalize_visible_text(value)
            if cleaned:
                return cleaned
    return None


def extract_blurb_after_team_section_heading(page_text: str) -> str | None:
    """Pull the paragraph immediately under OUR FOUNDERS / Meet the team-style headings."""

    lines = page_text.splitlines()
    for index, line in enumerate(lines):
        heading_key = normalize_visible_text(line).lower().rstrip(":")
        if heading_key not in _FOUNDER_SECTION_HEADINGS:
            continue
        cursor = index + 1
        while cursor < len(lines) and (
            not lines[cursor].strip() or _UNDERLINE_HEADING_LINE.match(lines[cursor])
        ):
            cursor += 1
        paragraph_lines: list[str] = []
        while cursor < len(lines):
            raw_line = lines[cursor]
            stripped = raw_line.strip()
            if not stripped:
                break
            if stripped.startswith("#"):
                break
            if stripped.startswith("!["):
                cursor += 1
                continue
            if _FOUNDER_ROLE_LINE.match(stripped):
                break
            paragraph_lines.append(raw_line)
            cursor += 1
        if not paragraph_lines:
            return None
        text = normalize_visible_text("\n".join(paragraph_lines))
        return text if len(text) >= 12 else None
    return None


def paragraph_looks_like_markdown_breadcrumb(paragraph: str) -> bool:
    """True when a paragraph is mostly a nav crumb like '[Home](url) Our Team'."""

    cleaned = normalize_visible_text(paragraph)
    if not _MARKDOWN_INLINE_LINK.search(cleaned):
        return False
    remainder = normalize_visible_text(_MARKDOWN_INLINE_LINK.sub("", cleaned))
    return len(remainder) < _MIN_DESCRIPTION_CHARS


def extract_founder_segments(page_text: str) -> list[str]:
    """Extract founder name and role segments from page text."""

    founder_line = extract_labeled_line(page_text, "Founders")
    if founder_line:
        return [
            segment.strip()
            for segment in re.split(r"\s+and\s+", founder_line)
            if segment.strip()
        ]

    return extract_founder_segments_from_team_member_roles(page_text)


def extract_founder_segments_from_team_member_roles(page_text: str) -> list[str]:
    """Parse founder name + role blocks common on marketing team pages."""

    lines = page_text.splitlines()
    segments: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not _FOUNDER_ROLE_LINE.match(stripped):
            continue
        role_title = normalize_visible_text(stripped)
        name_line = _find_preceding_team_member_name_line(lines, index)
        if not name_line:
            continue
        founder_name = normalize_visible_text(name_line)
        if not founder_name:
            continue
        segments.append(f"{founder_name}, {role_title}")

    return segments


def _find_preceding_team_member_name_line(lines: list[str], role_line_index: int) -> str | None:
    """Walk upward from a 'Founder, …' role line to the nearest plausible full-name line."""

    index = role_line_index - 1
    while index >= 0:
        candidate = lines[index].strip()
        if not candidate:
            index -= 1
            continue
        if candidate.startswith("!["):
            index -= 1
            continue
        if _UNDERLINE_HEADING_LINE.match(candidate):
            index -= 1
            continue
        if _MARKDOWN_LINK_ONLY_LINE.match(candidate):
            index -= 1
            continue
        if candidate.startswith("#"):
            index -= 1
            continue
        return candidate
    return None


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
