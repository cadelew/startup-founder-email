from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import NormalizedFounderRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.enrich import (
    canonicalize_company_domain,
    enrich_normalized_founder_record,
    run_enrichment_stage,
)


def test_canonicalize_company_domain_strips_scheme_and_www() -> None:
    assert canonicalize_company_domain("https://www.Example.com/about") == "example.com"


def test_enrich_normalized_founder_record_skips_mx_offline() -> None:
    normalized_founder_record = build_normalized_founder_record()

    enrichment_record = enrich_normalized_founder_record(normalized_founder_record)

    assert enrichment_record.canonical_company_domain == "example.com"
    assert enrichment_record.has_mx_records is False
    assert enrichment_record.enrichment_notes == ("mx_skipped_offline",)


def test_run_enrichment_stage_writes_enriched_jsonl(tmp_path) -> None:
    context = build_pipeline_context(tmp_path)
    normalized_path = context.config.output_directories.normalized_directory / "items.jsonl"
    write_jsonl_records(normalized_path, [build_normalized_founder_record()])

    exit_code = run_enrichment_stage(context)
    output_path = context.config.output_directories.enriched_directory / "items.jsonl"
    enrichment_records = list(iter_jsonl_records(output_path))

    assert exit_code == 0
    assert enrichment_records[0]["canonical_company_domain"] == "example.com"
    assert enrichment_records[0]["enrichment_notes"] == ["mx_skipped_offline"]


def build_normalized_founder_record() -> NormalizedFounderRecord:
    return NormalizedFounderRecord(
        company_name="Example",
        batch_name=None,
        industry_name=None,
        company_website_url="https://www.Example.com/about",
        raw_company_description="Example builds tools.",
        founder_full_name="Ada Lovelace",
        founder_first_name="Ada",
        founder_last_name="Lovelace",
        founder_role_title="CTO",
        founder_linkedin_url=None,
        source_url="https://www.Example.com/about",
    )
