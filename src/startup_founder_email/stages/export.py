"""Final export stage entrypoint."""

from __future__ import annotations

import csv
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

from startup_founder_email.jsonl_io import iter_jsonl_records
from startup_founder_email.models import ContactCandidateRecord
from startup_founder_email.pipeline import PipelineContext

logger = logging.getLogger(__name__)

EXPORT_COLUMNS: tuple[str, ...] = (
    "founder_full_name",
    "company_name",
    "company_website_url",
    "canonical_company_domain",
    "public_email_address",
    "public_email_source_type",
    "best_email_guess",
    "alternative_email_guess",
    "email_source_type",
    "email_confidence_level",
    "syntax_valid",
    "is_role_address",
    "is_disposable_domain",
    "mx_provider_known",
    "smtp_probe_status",
    "validation_notes",
    "company_summary",
    "founder_linkedin_url",
    "source_url",
    "status",
    "notes",
)


def run_export_stage(context: PipelineContext) -> int:
    """Export validated contact candidates to CSV."""

    contact_candidate_records = read_validated_contact_candidate_records(context)
    output_path = context.config.output_directories.exported_directory / "contacts.csv"
    write_contact_candidates_csv(output_path, contact_candidate_records)

    logger.info("Wrote %s exported contacts to %s", len(contact_candidate_records), output_path)
    return 0


def write_contact_candidates_csv(
    output_path: Path,
    contact_candidate_records: list[ContactCandidateRecord],
) -> None:
    """Write contact candidate records to a stable-column CSV."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for contact_candidate_record in contact_candidate_records:
            writer.writerow(build_export_row(contact_candidate_record))


def build_export_row(contact_candidate_record: ContactCandidateRecord) -> dict[str, Any]:
    """Build one CSV row from a contact candidate record."""

    record_dictionary = asdict(contact_candidate_record)
    return {
        column_name: format_csv_value(record_dictionary.get(column_name))
        for column_name in EXPORT_COLUMNS
    }


def format_csv_value(value: object) -> object:
    """Format nested values for CSV output."""

    if isinstance(value, tuple):
        return "; ".join(value)
    if value is None:
        return ""
    return value


def read_validated_contact_candidate_records(
    context: PipelineContext,
) -> list[ContactCandidateRecord]:
    """Read validated contact candidate records from JSONL."""

    input_path = context.config.output_directories.validated_directory / "items.jsonl"
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
