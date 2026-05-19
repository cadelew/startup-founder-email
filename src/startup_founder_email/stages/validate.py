"""Validation stage entrypoint."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any

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
    smtp_probe_status = "skipped"
    smtp_probe_notes: tuple[str, ...] = ()

    if validation_config.enable_reacher_http_validation and syntax_valid and email_address:
        try:
            smtp_probe_status, smtp_probe_notes = probe_reacher_http_validation(
                validation_config,
                email_address,
            )
        except RuntimeError as error:
            logger.warning(str(error))
            smtp_probe_status = "error"
            smtp_probe_notes = ("smtp_probe_http_error",)

    validation_notes = build_validation_notes(
        syntax_valid,
        is_role_address,
        is_disposable_domain,
        mx_provider_known,
        smtp_probe_status,
        smtp_probe_notes,
    )

    if validation_config.enable_smtp_probe:
        raise NotImplementedError("SMTP probing is intentionally disabled offline.")

    return replace(
        contact_candidate_record,
        syntax_valid=syntax_valid,
        is_role_address=is_role_address,
        is_disposable_domain=is_disposable_domain,
        mx_provider_known=mx_provider_known,
        smtp_probe_status=smtp_probe_status,
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
    smtp_probe_status: str,
    smtp_probe_notes: tuple[str, ...] = (),
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
    if smtp_probe_status == "skipped":
        validation_notes.append("smtp_skipped_offline")
    validation_notes.extend(smtp_probe_notes)
    return tuple(validation_notes)


def probe_reacher_http_validation(
    validation_config: ValidationConfig,
    email_address: str,
) -> tuple[str, tuple[str, ...]]:
    """Call Reacher's HTTP API and map response fields to status/notes."""

    reacher_payload = post_reacher_check_email_request(
        validation_config,
        email_address,
    )
    return map_reacher_payload_to_smtp_status(reacher_payload)


def post_reacher_check_email_request(
    validation_config: ValidationConfig,
    email_address: str,
) -> dict[str, Any]:
    """POST one email to Reacher `/v0/check_email` and parse the response."""

    request_body = json.dumps({"to_email": email_address}).encode("utf-8")
    request = urllib.request.Request(
        f"{validation_config.reacher_base_url.rstrip('/')}/v0/check_email",
        data=request_body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=validation_config.reacher_timeout_seconds,
        ) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        raise RuntimeError(f"Reacher HTTP probe failed for {email_address}: {error}") from error

    if not isinstance(response_payload, dict):
        raise RuntimeError("Reacher returned a non-object JSON response.")
    return response_payload


def map_reacher_payload_to_smtp_status(
    reacher_payload: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    """Map Reacher HTTP response fields to `smtp_probe_status` and notes."""

    smtp_payload = reacher_payload.get("smtp")
    if not isinstance(smtp_payload, dict):
        return "error", ("smtp_probe_response_missing_smtp",)

    is_catch_all = bool(smtp_payload.get("is_catch_all"))
    is_disabled = bool(smtp_payload.get("is_disabled"))
    has_full_inbox = bool(smtp_payload.get("has_full_inbox"))
    is_deliverable = smtp_payload.get("is_deliverable")
    can_connect_smtp = smtp_payload.get("can_connect_smtp")

    if is_catch_all:
        return "catch_all", ("smtp_probe_catch_all",)
    if is_disabled:
        return "undeliverable", ("smtp_probe_mailbox_disabled",)
    if has_full_inbox:
        return "undeliverable", ("smtp_probe_inbox_full",)
    if is_deliverable is True:
        return "deliverable", ("smtp_probe_deliverable",)
    if is_deliverable is False:
        return "undeliverable", ("smtp_probe_undeliverable",)
    if can_connect_smtp is False:
        return "error", ("smtp_probe_connection_failed",)
    return "error", ("smtp_probe_inconclusive",)


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
