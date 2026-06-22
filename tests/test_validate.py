from pathlib import Path

from startup_founder_email.config import ValidationConfig
from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import ContactCandidateRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.validate import (
    adjust_confidence_from_validation,
    check_domain_a_record,
    has_free_email_domain,
    has_short_local_part,
    map_reacher_payload_to_smtp_status,
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


def test_validate_contact_candidate_runs_reacher_probe_when_enabled(monkeypatch) -> None:
    contact_candidate_record = build_contact_candidate_record(best_email_guess="ada@example.com")
    validation_config = ValidationConfig(
        enable_reacher_http_validation=True,
        reacher_base_url="http://localhost:8080",
        reacher_timeout_seconds=20.0,
        disposable_domains_path=None,
    )

    monkeypatch.setattr(
        "startup_founder_email.stages.validate.post_reacher_check_email_request",
        lambda _validation_config, _email: {
            "smtp": {
                "is_deliverable": True,
                "is_disabled": False,
                "has_full_inbox": False,
                "is_catch_all": False,
                "can_connect_smtp": True,
            }
        },
    )

    validated_record = validate_contact_candidate(
        contact_candidate_record,
        validation_config,
        set(),
    )

    assert validated_record.smtp_probe_status == "deliverable"
    assert "smtp_probe_deliverable" in validated_record.validation_notes
    assert "smtp_skipped_offline" not in validated_record.validation_notes


def test_validate_contact_candidate_sets_error_when_reacher_http_fails(monkeypatch) -> None:
    contact_candidate_record = build_contact_candidate_record(best_email_guess="ada@example.com")
    validation_config = ValidationConfig(
        enable_reacher_http_validation=True,
        reacher_base_url="http://localhost:8080",
        reacher_timeout_seconds=20.0,
        disposable_domains_path=None,
    )

    def raise_http_error(_validation_config, _email):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "startup_founder_email.stages.validate.post_reacher_check_email_request",
        raise_http_error,
    )

    validated_record = validate_contact_candidate(
        contact_candidate_record,
        validation_config,
        set(),
    )

    assert validated_record.smtp_probe_status == "error"
    assert "smtp_probe_http_error" in validated_record.validation_notes


def test_validate_contact_candidate_skips_reacher_probe_for_invalid_syntax(monkeypatch) -> None:
    contact_candidate_record = build_contact_candidate_record(best_email_guess="invalid-email")
    validation_config = ValidationConfig(
        enable_reacher_http_validation=True,
        reacher_base_url="http://localhost:8080",
        reacher_timeout_seconds=20.0,
        disposable_domains_path=None,
    )
    called = {"count": 0}

    def fake_post_reacher(_validation_config, _email):
        called["count"] += 1
        return {}

    monkeypatch.setattr(
        "startup_founder_email.stages.validate.post_reacher_check_email_request",
        fake_post_reacher,
    )

    validated_record = validate_contact_candidate(
        contact_candidate_record,
        validation_config,
        set(),
    )

    assert called["count"] == 0
    assert validated_record.syntax_valid is False
    assert validated_record.smtp_probe_status == "skipped"


def test_map_reacher_payload_to_smtp_status_handles_catch_all() -> None:
    status, notes = map_reacher_payload_to_smtp_status(
        {
            "smtp": {
                "is_catch_all": True,
                "is_deliverable": True,
                "is_disabled": False,
                "has_full_inbox": False,
            }
        }
    )

    assert status == "catch_all"
    assert notes == ("smtp_probe_catch_all",)


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


def test_has_free_email_domain_detects_free_providers() -> None:
    free_domains = ("gmail.com", "yahoo.com", "outlook.com")
    assert has_free_email_domain("john@gmail.com", free_domains) is True
    assert has_free_email_domain("john@yahoo.com", free_domains) is True
    assert has_free_email_domain("john@company.com", free_domains) is False
    assert has_free_email_domain(None, free_domains) is False


def test_has_short_local_part_flags_short_usernames() -> None:
    assert has_short_local_part("ab@example.com", 3) is True
    assert has_short_local_part("a@example.com", 3) is True
    assert has_short_local_part("abc@example.com", 3) is False
    assert has_short_local_part("ada.lovelace@example.com", 3) is False
    assert has_short_local_part(None, 3) is False


def test_check_domain_a_record_resolves_real_domains() -> None:
    assert check_domain_a_record("google.com", 3.0) is True
    assert check_domain_a_record("this-domain-does-not-exist-12345.example", 3.0) is False


def test_adjust_confidence_downgrades_for_free_email() -> None:
    result = adjust_confidence_from_validation(
        "medium", True, False, True, False, False, True, True, "skipped"
    )
    assert result == "low"


def test_adjust_confidence_downgrades_for_unresolvable_domain() -> None:
    result = adjust_confidence_from_validation(
        "medium", True, False, False, False, False, False, False, "skipped"
    )
    assert result == "none"


def test_adjust_confidence_downgrades_for_short_local_part() -> None:
    result = adjust_confidence_from_validation(
        "medium", True, False, False, False, True, True, True, "skipped"
    )
    assert result == "low"


def test_validate_contact_candidate_detects_free_email_domain() -> None:
    contact_candidate_record = build_contact_candidate_record(
        best_email_guess="founder@gmail.com"
    )
    validation_config = ValidationConfig(
        enable_domain_a_record_check=False,
        free_email_domains=("gmail.com",),
    )

    validated_record = validate_contact_candidate(
        contact_candidate_record,
        validation_config,
        set(),
    )

    assert validated_record.is_free_email_domain is True
    assert "free_email_domain" in validated_record.validation_notes
    assert validated_record.email_confidence_level == "low"


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
