"""Domain enrichment stage entrypoint."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import DomainEnrichmentRecord, NormalizedFounderRecord
from startup_founder_email.pipeline import PipelineContext

logger = logging.getLogger(__name__)


def run_enrichment_stage(context: PipelineContext) -> int:
    """Enrich normalized records with offline domain metadata."""

    normalized_founder_records = read_normalized_founder_records(context)
    enrichment_records = enrich_normalized_founder_records(normalized_founder_records)
    output_path = context.config.output_directories.enriched_directory / "items.jsonl"
    write_jsonl_records(output_path, enrichment_records)

    logger.info("Wrote %s enrichment records to %s", len(enrichment_records), output_path)
    return 0


def read_normalized_founder_records(
    context: PipelineContext,
) -> list[NormalizedFounderRecord]:
    """Read normalized founder records from JSONL."""

    input_path = context.config.output_directories.normalized_directory / "items.jsonl"
    return [
        NormalizedFounderRecord(
            company_name=str(record.get("company_name", "")),
            batch_name=read_optional_string(record.get("batch_name")),
            industry_name=read_optional_string(record.get("industry_name")),
            company_website_url=read_optional_string(record.get("company_website_url")),
            raw_company_description=read_optional_string(
                record.get("raw_company_description")
            ),
            founder_full_name=str(record.get("founder_full_name", "")),
            founder_first_name=read_optional_string(record.get("founder_first_name")),
            founder_last_name=read_optional_string(record.get("founder_last_name")),
            founder_role_title=read_optional_string(record.get("founder_role_title")),
            founder_linkedin_url=read_optional_string(record.get("founder_linkedin_url")),
            source_url=str(record.get("source_url", "")),
            public_email_address=read_optional_string(record.get("public_email_address")),
            public_email_source_type=str(record.get("public_email_source_type", "")),
            cleaning_notes=tuple(read_string_items(record.get("cleaning_notes"))),
        )
        for record in iter_jsonl_records(input_path)
    ]


def enrich_normalized_founder_records(
    normalized_founder_records: list[NormalizedFounderRecord],
) -> list[DomainEnrichmentRecord]:
    """Build one enrichment record per unique company/domain pair."""

    enrichment_records_by_key: dict[tuple[str, str | None], DomainEnrichmentRecord] = {}
    for normalized_founder_record in normalized_founder_records:
        enrichment_record = enrich_normalized_founder_record(normalized_founder_record)
        key = (
            enrichment_record.company_name,
            enrichment_record.canonical_company_domain,
        )
        enrichment_records_by_key[key] = enrichment_record

    return list(enrichment_records_by_key.values())


def enrich_normalized_founder_record(
    normalized_founder_record: NormalizedFounderRecord,
) -> DomainEnrichmentRecord:
    """Build offline enrichment metadata for one normalized record."""

    final_website_url = normalized_founder_record.company_website_url
    canonical_company_domain = canonicalize_company_domain(final_website_url)
    enrichment_notes = ("mx_skipped_offline",)
    if canonical_company_domain is None:
        enrichment_notes = ("domain_not_found", "mx_skipped_offline")

    return DomainEnrichmentRecord(
        company_name=normalized_founder_record.company_name,
        raw_company_description=normalized_founder_record.raw_company_description,
        canonical_company_domain=canonical_company_domain,
        final_website_url=final_website_url,
        has_mx_records=False,
        mx_provider_name=None,
        enrichment_notes=enrichment_notes,
    )


def canonicalize_company_domain(website_url: str | None) -> str | None:
    """Return a lowercase domain without a leading www."""

    if not website_url:
        return None

    parsed_url = urlparse(website_url if "://" in website_url else f"https://{website_url}")
    hostname = parsed_url.hostname
    if not hostname:
        return None

    lowercase_hostname = hostname.lower()
    if lowercase_hostname.startswith("www."):
        return lowercase_hostname[4:]
    return lowercase_hostname


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
