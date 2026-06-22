"""Contact generation stage entrypoint."""

from __future__ import annotations

import logging

from startup_founder_email.config import EmailInferenceConfig
from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import (
    ContactCandidateRecord,
    DomainEnrichmentRecord,
    NormalizedFounderRecord,
)
from startup_founder_email.pipeline import PipelineContext
from startup_founder_email.text_normalization import (
    normalize_email_token,
    normalize_visible_text,
)

logger = logging.getLogger(__name__)


def run_contact_generation_stage(context: PipelineContext) -> int:
    """Generate contact candidates from normalized founder records."""

    normalized_founder_records = read_normalized_founder_records(context)
    enrichment_records = read_enrichment_records(context)
    contact_candidate_records = generate_contact_candidates(
        normalized_founder_records,
        enrichment_records,
        context.config.email_inference,
    )
    output_path = context.config.output_directories.generated_directory / "items.jsonl"
    write_jsonl_records(output_path, contact_candidate_records)

    logger.info(
        "Wrote %s contact candidates to %s",
        len(contact_candidate_records),
        output_path,
    )
    return 0


def generate_contact_candidates(
    normalized_founder_records: list[NormalizedFounderRecord],
    enrichment_records: list[DomainEnrichmentRecord],
    email_inference_config: EmailInferenceConfig,
) -> list[ContactCandidateRecord]:
    """Generate contact candidates for normalized founder rows."""

    enrichment_records_by_company_and_url = {
        build_enrichment_lookup_key(enrichment_record): enrichment_record
        for enrichment_record in enrichment_records
    }
    return [
        generate_contact_candidate(
            normalized_founder_record,
            enrichment_records_by_company_and_url.get(
                build_normalized_lookup_key(normalized_founder_record)
            ),
            email_inference_config,
        )
        for normalized_founder_record in normalized_founder_records
    ]


def generate_contact_candidate(
    normalized_founder_record: NormalizedFounderRecord,
    enrichment_record: DomainEnrichmentRecord | None,
    email_inference_config: EmailInferenceConfig,
) -> ContactCandidateRecord:
    """Generate one contact candidate for a normalized founder row."""

    canonical_company_domain = (
        enrichment_record.canonical_company_domain if enrichment_record else None
    )
    inferred_email_addresses = infer_email_addresses(
        normalized_founder_record,
        canonical_company_domain,
        email_inference_config.email_patterns,
    )
    public_email_address = normalized_founder_record.public_email_address
    public_email_source_type = normalized_founder_record.public_email_source_type
    best_email_guess = choose_best_email_guess(
        public_email_address,
        public_email_source_type,
        inferred_email_addresses,
    )
    email_source_type = choose_email_source_type(
        public_email_address,
        public_email_source_type,
        best_email_guess,
        inferred_email_addresses,
    )
    email_confidence_level = choose_email_confidence_level(
        public_email_address,
        public_email_source_type,
        inferred_email_addresses,
        canonical_company_domain,
    )

    return ContactCandidateRecord(
        founder_full_name=normalized_founder_record.founder_full_name,
        company_name=normalized_founder_record.company_name,
        batch_name=normalized_founder_record.batch_name,
        industry_name=normalized_founder_record.industry_name,
        company_website_url=normalized_founder_record.company_website_url,
        raw_company_description=normalized_founder_record.raw_company_description,
        company_summary=build_company_summary(
            normalized_founder_record.raw_company_description
        ),
        canonical_company_domain=canonical_company_domain,
        public_email_address=public_email_address,
        public_email_source_type=public_email_source_type,
        best_email_guess=best_email_guess,
        alternative_email_guess=choose_alternative_email_guess(
            public_email_address,
            public_email_source_type,
            inferred_email_addresses,
        ),
        all_inferred_email_guesses=tuple(inferred_email_addresses),
        email_source_type=email_source_type,
        email_confidence_level=email_confidence_level,
        mx_provider_name=enrichment_record.mx_provider_name if enrichment_record else None,
        founder_linkedin_url=normalized_founder_record.founder_linkedin_url,
        source_url=normalized_founder_record.source_url,
    )


def build_enrichment_lookup_key(
    enrichment_record: DomainEnrichmentRecord,
) -> tuple[str, str | None]:
    """Build the key used to match enrichment data to normalized rows."""

    return enrichment_record.company_name, enrichment_record.final_website_url


def build_normalized_lookup_key(
    normalized_founder_record: NormalizedFounderRecord,
) -> tuple[str, str | None]:
    """Build the key used to find enrichment data for a normalized row."""

    return (
        normalized_founder_record.company_name,
        normalized_founder_record.company_website_url,
    )


def infer_email_addresses(
    normalized_founder_record: NormalizedFounderRecord,
    canonical_company_domain: str | None,
    email_patterns: tuple[str, ...],
) -> list[str]:
    """Infer possible email addresses for one founder/domain pair."""

    if not canonical_company_domain or not normalized_founder_record.founder_first_name:
        return []
    if not normalized_founder_record.founder_last_name:
        return []

    token_values = build_email_pattern_tokens(normalized_founder_record)
    inferred_local_parts = [
        email_pattern.format(**token_values)
        for email_pattern in email_patterns
    ]
    return [
        f"{local_part}@{canonical_company_domain}"
        for local_part in deduplicate_strings(inferred_local_parts)
        if local_part
    ]


def build_email_pattern_tokens(
    normalized_founder_record: NormalizedFounderRecord,
) -> dict[str, str]:
    """Build the supported token values for email inference patterns."""

    first_name = normalize_email_token(normalized_founder_record.founder_first_name)
    last_name = normalize_email_token(normalized_founder_record.founder_last_name)
    return {
        "first": first_name,
        "last": last_name,
        "f": first_name[:1],
        "l": last_name[:1],
    }


def choose_best_email_guess(
    public_email_address: str | None,
    public_email_source_type: str,
    inferred_email_addresses: list[str],
) -> str | None:
    """Choose the best email guess to show in the exported row.

    Prefers a personal public email (source_type="person") over inferred.
    When the public email is only company-level (hello@, info@), prefer the
    first inferred personal email since it targets the founder directly.
    """

    if public_email_address and public_email_source_type == "person":
        return public_email_address
    if inferred_email_addresses:
        return inferred_email_addresses[0]
    if public_email_address:
        return public_email_address
    return None


def choose_alternative_email_guess(
    public_email_address: str | None,
    public_email_source_type: str,
    inferred_email_addresses: list[str],
) -> str | None:
    """Choose the second-best email guess.

    When the best guess is an inferred email, the alternative is the next
    inferred pattern. When the best guess is a personal public email, the
    first inferred pattern is the alternative.
    """

    if public_email_address and public_email_source_type == "person":
        if inferred_email_addresses:
            return inferred_email_addresses[0]
        return None
    if inferred_email_addresses:
        if len(inferred_email_addresses) > 1:
            return inferred_email_addresses[1]
        if public_email_address:
            return public_email_address
    return None


def choose_email_confidence_level(
    public_email_address: str | None,
    public_email_source_type: str,
    inferred_email_addresses: list[str],
    canonical_company_domain: str | None,
) -> str:
    """Choose a simple confidence label for a contact candidate."""

    if public_email_address and public_email_source_type == "person":
        return "high"
    if inferred_email_addresses and canonical_company_domain:
        return "medium"
    if public_email_address and public_email_source_type == "company":
        return "low"
    return "low"


def choose_email_source_type(
    public_email_address: str | None,
    public_email_source_type: str,
    best_email_guess: str | None,
    inferred_email_addresses: list[str],
) -> str:
    """Choose a source label for the selected email address."""

    if public_email_address and public_email_source_type == "person":
        return "public_person"
    if best_email_guess and best_email_guess in inferred_email_addresses:
        return "inferred"
    if public_email_address and public_email_source_type == "company":
        return "public_company"
    if public_email_address:
        return "public"
    return "inferred"


def build_company_summary(raw_company_description: str | None) -> str | None:
    """Build a short company summary from the raw description."""

    if not raw_company_description:
        return None
    return normalize_visible_text(raw_company_description)


def deduplicate_strings(values: list[str]) -> list[str]:
    """Deduplicate strings while preserving order."""

    seen_values: set[str] = set()
    deduplicated_values: list[str] = []
    for value in values:
        if value not in seen_values:
            seen_values.add(value)
            deduplicated_values.append(value)
    return deduplicated_values


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
            seed_url=read_optional_string(record.get("seed_url")),
            public_email_address=read_optional_string(record.get("public_email_address")),
            public_email_source_type=str(record.get("public_email_source_type", "")),
            cleaning_notes=tuple(read_string_items(record.get("cleaning_notes"))),
        )
        for record in iter_jsonl_records(input_path)
    ]


def read_enrichment_records(context: PipelineContext) -> list[DomainEnrichmentRecord]:
    """Read domain enrichment records from JSONL."""

    input_path = context.config.output_directories.enriched_directory / "items.jsonl"
    return [
        DomainEnrichmentRecord(
            company_name=str(record.get("company_name", "")),
            raw_company_description=read_optional_string(
                record.get("raw_company_description")
            ),
            canonical_company_domain=read_optional_string(
                record.get("canonical_company_domain")
            ),
            final_website_url=read_optional_string(record.get("final_website_url")),
            has_mx_records=bool(record.get("has_mx_records")),
            mx_provider_name=read_optional_string(record.get("mx_provider_name")),
            enrichment_notes=tuple(read_string_items(record.get("enrichment_notes"))),
        )
        for record in iter_jsonl_records(input_path)
    ]


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
