import csv

from startup_founder_email.jsonl_io import write_jsonl_records
from startup_founder_email.models import ContactCandidateRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.export import (
    build_export_row,
    run_export_stage,
    write_contact_candidates_csv,
)


def test_build_export_row_formats_validation_notes() -> None:
    contact_candidate_record = build_contact_candidate_record()

    export_row = build_export_row(contact_candidate_record)

    assert export_row["validation_notes"] == "mx_unknown_offline; smtp_skipped_offline"
    assert export_row["best_email_guess"] == "ada@example.com"


def test_write_contact_candidates_csv_writes_stable_columns(tmp_path) -> None:
    output_path = tmp_path / "contacts.csv"

    write_contact_candidates_csv(output_path, [build_contact_candidate_record()])

    with output_path.open(encoding="utf-8", newline="") as output_file:
        rows = list(csv.DictReader(output_file))

    assert rows[0]["founder_full_name"] == "Ada Lovelace"
    assert rows[0]["smtp_probe_status"] == "skipped"


def test_run_export_stage_writes_contacts_csv(tmp_path) -> None:
    context = build_pipeline_context(tmp_path)
    validated_path = context.config.output_directories.validated_directory / "items.jsonl"
    write_jsonl_records(validated_path, [build_contact_candidate_record()])

    exit_code = run_export_stage(context)
    output_path = context.config.output_directories.exported_directory / "contacts.csv"

    assert exit_code == 0
    assert output_path.exists()


def build_contact_candidate_record() -> ContactCandidateRecord:
    return ContactCandidateRecord(
        founder_full_name="Ada Lovelace",
        company_name="Example",
        batch_name=None,
        industry_name=None,
        company_website_url="https://example.com",
        raw_company_description="Example builds tools.",
        company_summary="Example builds tools.",
        canonical_company_domain="example.com",
        public_email_address=None,
        public_email_source_type="",
        best_email_guess="ada@example.com",
        alternative_email_guess="ada.lovelace@example.com",
        email_source_type="inferred",
        email_confidence_level="medium",
        mx_provider_name=None,
        founder_linkedin_url=None,
        source_url="https://example.com",
        syntax_valid=True,
        smtp_probe_status="skipped",
        validation_notes=("mx_unknown_offline", "smtp_skipped_offline"),
    )
