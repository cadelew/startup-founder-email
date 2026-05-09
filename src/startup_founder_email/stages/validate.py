"""Validation stage entrypoint."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path

from startup_founder_email.config import ValidationConfig
from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import ContactCandidateRecord
from startup_founder_email.pipeline import PipelineContext

logger = logging.getLogger(__name__)

EMAIL_ADDRESS_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def run_validation_stage(context: PipelineContext) -> int:
    """Validate generated contact candidates with offline checks."""

    contact_candidate_records = read_contact_candidate_records(context)
    validated_contact_candidate_records = validate_contact_candidates(
        contact_candidate_records,
        context.config.validation,
    )
    output_path = context.config.output_directories.validated_directory / "items.jsonl"
    write_jsonl_records(output_path, validated_contact_candidate_records)

    logger.info(
        "Wrote %s validated contact candidates to %s",
        len(validated_contact_candidate_records),
        output_path,
    )
    return 0


def validate_contact_candidates(
    contact_candidate_records: list[ContactCandidateRecord],
    validation_config: ValidationConfig,
) -> list[ContactCandidateRecord]:
    """Validate contact candidates using offline email checks."""

    disposable_domains = read_disposable_domains(validation_config.disposable_domains_path)
    return [
        validate_contact_candidate(
            contact_candidate_record,
            validation_config,
            disposable_domains,
        )
        for contact_candidate_record in contact_candidate_records
    ]


def validate_contact_candidate(
    contact_candidate_record: ContactCandidateRecord,
    validation_config: ValidationConfig,
    disposable_domains: set[str],
) -> ContactCandidateRecord:
    """Validate one contact candidate."""

    email_address = choose_email_address_to_validate(contact_candidate_record)
    syntax_valid = is_syntax_valid(email_address)
    is_role_address = has_role_local_part(
        email_address,
        validation_config.role_local_parts,
    )
    is_disposable_domain = has_disposable_domain(email_address, disposable_domains)
    mx_provider_known = contact_candidate_record.mx_provider_name is not None
    validation_notes = build_validation_notes(
        syntax_valid,
        is_role_address,
        is_disposable_domain,
        mx_provider_known,
    )

    if validation_config.enable_smtp_probe:
        raise NotImplementedError("SMTP probing is intentionally disabled offline.")

    return replace(
        contact_candidate_record,
        syntax_valid=syntax_valid,
        is_role_address=is_role_address,
        is_disposable_domain=is_disposable_domain,
        mx_provider_known=mx_provider_known,
        smtp_probe_status="skipped",
        validation_notes=validation_notes,
    )


def choose_email_address_to_validate(
    contact_candidate_record: ContactCandidateRecord,
) -> str | None:
    """Choose the email value that validation checks should inspect."""

    return (
        contact_candidate_record.best_email_guess
        or contact_candidate_record.public_email_address
    )


def is_syntax_valid(email_address: str | None) -> bool:
    """Return whether an email address has a basic valid shape."""

    if not email_address:
        return False
    return EMAIL_ADDRESS_PATTERN.match(email_address) is not None


def has_role_local_part(
    email_address: str | None,
    role_local_parts: tuple[str, ...],
) -> bool:
    """Return whether the email local part is role-based."""

    if not email_address or "@" not in email_address:
        return False
    local_part = email_address.split("@", 1)[0].lower()
    return local_part in set(role_local_parts)


def has_disposable_domain(
    email_address: str | None,
    disposable_domains: set[str],
) -> bool:
    """Return whether the email domain is known disposable mail."""

    if not email_address or "@" not in email_address:
        return False
    domain = email_address.rsplit("@", 1)[1].lower()
    return domain in disposable_domains


def build_validation_notes(
    syntax_valid: bool,
    is_role_address: bool,
    is_disposable_domain: bool,
    mx_provider_known: bool,
) -> tuple[str, ...]:
    """Build readable validation notes."""

    validation_notes: list[str] = []
    if not syntax_valid:
        validation_notes.append("invalid_syntax")
    if is_role_address:
        validation_notes.append("role_address")
    if is_disposable_domain:
        validation_notes.append("disposable_domain")
    if not mx_provider_known:
        validation_notes.append("mx_unknown_offline")
    validation_notes.append("smtp_skipped_offline")
    return tuple(validation_notes)


def read_disposable_domains(disposable_domains_path: Path | None) -> set[str]:
    """Read disposable domains from a newline-delimited text file."""

    if disposable_domains_path is None or not disposable_domains_path.exists():
        return set()
    return {
        line.strip().lower()
        for line in disposable_domains_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def read_contact_candidate_records(
    context: PipelineContext,
) -> list[ContactCandidateRecord]:
    """Read generated contact candidate records from JSONL."""

    input_path = context.config.output_directories.generated_directory / "items.jsonl"
    return [
        ContactCandidateRecord(
            founder_full_name=str(record.get("founder_full_name", "")),
            company_name=str(record.get("company_name", "")),
            batch_name=read_optional_string(record.get("batch_name")),
            industry_name=read_optional_string(record.get("industry_name")),
            company_website_url=read_optional_string(record.get("company_website_url")),
            raw_company_description=read_optional_string(
                record.get("raw_company_description")
            ),
            company_summary=read_optional_string(record.get("company_summary")),
            canonical_company_domain=read_optional_string(
                record.get("canonical_company_domain")
            ),
            public_email_address=read_optional_string(record.get("public_email_address")),
            public_email_source_type=str(record.get("public_email_source_type", "")),
            best_email_guess=read_optional_string(record.get("best_email_guess")),
            alternative_email_guess=read_optional_string(
                record.get("alternative_email_guess")
            ),
            email_source_type=str(record.get("email_source_type", "")),
            email_confidence_level=str(record.get("email_confidence_level", "")),
            mx_provider_name=read_optional_string(record.get("mx_provider_name")),
            founder_linkedin_url=read_optional_string(record.get("founder_linkedin_url")),
            source_url=str(record.get("source_url", "")),
            syntax_valid=bool(record.get("syntax_valid")),
            is_role_address=bool(record.get("is_role_address")),
            is_disposable_domain=bool(record.get("is_disposable_domain")),
            mx_provider_known=bool(record.get("mx_provider_known")),
            smtp_probe_status=str(record.get("smtp_probe_status", "skipped")),
            validation_notes=tuple(read_string_items(record.get("validation_notes"))),
            status=str(record.get("status", "")),
            notes=str(record.get("notes", "")),
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
