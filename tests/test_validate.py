from pathlib import Path

from startup_founder_email.config import ValidationConfig
from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import ContactCandidateRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.validate import (
    choose_email_address_to_validate,
    has_role_local_part,
    is_syntax_valid,
    read_disposable_domains,
    run_validation_stage,
    validate_contact_candidate,
)


def test_is_syntax_valid_checks_basic_email_shape() -> None:
    assert is_syntax_valid("ada@example.com") is True
    assert is_syntax_valid("ada.example.com") is False


def test_has_role_local_part_flags_role_addresses() -> None:
    assert has_role_local_part("hello@example.com", ("hello",)) is True
    assert has_role_local_part("ada@example.com", ("hello",)) is False


def test_read_disposable_domains_ignores_comments(tmp_path: Path) -> None:
    disposable_domains_path = tmp_path / "domains.txt"
    disposable_domains_path.write_text("# comment\nmailinator.com\n", encoding="utf-8")

    assert read_disposable_domains(disposable_domains_path) == {"mailinator.com"}


def test_validate_contact_candidate_sets_offline_flags(tmp_path: Path) -> None:
    contact_candidate_record = build_contact_candidate_record(
        best_email_guess="hello@mailinator.com"
    )
    validation_config = ValidationConfig(
        disposable_domains_path=None,
        role_local_parts=("hello",),
    )

    validated_record = validate_contact_candidate(
        contact_candidate_record,
        validation_config,
        {"mailinator.com"},
    )

    assert validated_record.syntax_valid is True
    assert validated_record.is_role_address is True
    assert validated_record.is_disposable_domain is True
    assert validated_record.smtp_probe_status == "skipped"


def test_choose_email_address_to_validate_falls_back_to_public_email() -> None:
    contact_candidate_record = build_contact_candidate_record(
        public_email_address="hello@example.com",
        best_email_guess=None,
    )

    assert choose_email_address_to_validate(contact_candidate_record) == "hello@example.com"


def test_run_validation_stage_writes_validated_jsonl(tmp_path: Path) -> None:
    context = build_pipeline_context(tmp_path)
    generated_path = context.config.output_directories.generated_directory / "items.jsonl"
    disposable_domains_path = (
        context.config.output_directories.validated_directory
        / "_disposable_domains.txt"
    )
    disposable_domains_path.write_text("mailinator.com\n", encoding="utf-8")
    write_jsonl_records(generated_path, [build_contact_candidate_record()])

    exit_code = run_validation_stage(context)
    output_path = context.config.output_directories.validated_directory / "items.jsonl"
    validated_records = list(iter_jsonl_records(output_path))

    assert exit_code == 0
    assert validated_records[0]["syntax_valid"] is True
    assert validated_records[0]["smtp_probe_status"] == "skipped"


def build_contact_candidate_record(
    best_email_guess: str = "ada@example.com",
    public_email_address: str | None = None,
) -> ContactCandidateRecord:
    return ContactCandidateRecord(
        founder_full_name="Ada Lovelace",
        company_name="Example",
        batch_name=None,
        industry_name=None,
        company_website_url="https://example.com",
        raw_company_description="Example builds tools.",
        company_summary="Example builds tools.",
        canonical_company_domain="example.com",
        public_email_address=public_email_address,
        public_email_source_type="company" if public_email_address else "",
        best_email_guess=best_email_guess,
        alternative_email_guess="ada.lovelace@example.com",
        email_source_type="inferred",
        email_confidence_level="medium",
        mx_provider_name=None,
        founder_linkedin_url=None,
        source_url="https://example.com",
    )
