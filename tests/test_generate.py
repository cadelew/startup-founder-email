from startup_founder_email.config import EmailInferenceConfig
from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import DomainEnrichmentRecord, NormalizedFounderRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.generate import (
    build_enrichment_lookup_key,
    build_normalized_lookup_key,
    generate_contact_candidate,
    generate_contact_candidates,
    infer_email_addresses,
    run_contact_generation_stage,
)


def test_infer_email_addresses_transliterates_accented_founder_names() -> None:
    normalized_founder_record = NormalizedFounderRecord(
        company_name="Tex Software",
        batch_name=None,
        industry_name=None,
        company_website_url="https://texsoftware.com/team",
        raw_company_description="Example",
        founder_full_name="Federico Chávez-Torres",
        founder_first_name="Federico",
        founder_last_name="Chávez-Torres",
        founder_role_title="Founder, CEO",
        founder_linkedin_url=None,
        source_url="https://texsoftware.com/team",
        public_email_address=None,
        public_email_source_type="",
    )

    email_addresses = infer_email_addresses(
        normalized_founder_record,
        "texsoftware.com",
        ("{first}.{last}",),
    )

    assert email_addresses == ["federico.chaveztorres@texsoftware.com"]


def test_infer_email_addresses_uses_configured_patterns() -> None:
    normalized_founder_record = build_normalized_founder_record()

    email_addresses = infer_email_addresses(
        normalized_founder_record,
        "example.com",
        ("{first}.{last}", "{f}{last}", "{first}.{l}"),
    )

    assert email_addresses == [
        "ada.lovelace@example.com",
        "alovelace@example.com",
        "ada.l@example.com",
    ]


def test_generate_contact_candidate_prefers_public_email() -> None:
    normalized_founder_record = build_normalized_founder_record(
        public_email_address="hello@example.com",
        public_email_source_type="company",
    )
    enrichment_record = build_enrichment_record()

    contact_candidate_record = generate_contact_candidate(
        normalized_founder_record,
        enrichment_record,
        EmailInferenceConfig(),
    )

    assert contact_candidate_record.best_email_guess == "hello@example.com"
    assert contact_candidate_record.email_source_type == "public_company"
    assert contact_candidate_record.email_confidence_level == "medium"


def test_generate_contact_candidates_matches_enrichment_by_company_and_url() -> None:
    normalized_founder_record = build_normalized_founder_record(
        company_website_url="https://right.example"
    )
    wrong_enrichment_record = build_enrichment_record(
        final_website_url="https://wrong.example",
        canonical_company_domain="wrong.example",
    )
    right_enrichment_record = build_enrichment_record(
        final_website_url="https://right.example",
        canonical_company_domain="right.example",
    )

    contact_candidate_records = generate_contact_candidates(
        [normalized_founder_record],
        [wrong_enrichment_record, right_enrichment_record],
        EmailInferenceConfig(),
    )

    assert contact_candidate_records[0].canonical_company_domain == "right.example"
    assert build_normalized_lookup_key(normalized_founder_record) == (
        "Example",
        "https://right.example",
    )
    assert build_enrichment_lookup_key(right_enrichment_record) == (
        "Example",
        "https://right.example",
    )


def test_run_contact_generation_stage_writes_generated_jsonl(tmp_path) -> None:
    context = build_pipeline_context(tmp_path)
    normalized_path = context.config.output_directories.normalized_directory / "items.jsonl"
    enriched_path = context.config.output_directories.enriched_directory / "items.jsonl"
    write_jsonl_records(normalized_path, [build_normalized_founder_record()])
    write_jsonl_records(enriched_path, [build_enrichment_record()])

    exit_code = run_contact_generation_stage(context)
    output_path = context.config.output_directories.generated_directory / "items.jsonl"
    contact_candidate_records = list(iter_jsonl_records(output_path))

    assert exit_code == 0
    assert contact_candidate_records[0]["best_email_guess"] == "ada.lovelace@example.com"
    assert contact_candidate_records[0]["email_source_type"] == "inferred"


def build_normalized_founder_record(
    public_email_address: str | None = None,
    public_email_source_type: str = "",
    company_website_url: str = "https://example.com",
) -> NormalizedFounderRecord:
    return NormalizedFounderRecord(
        company_name="Example",
        batch_name=None,
        industry_name=None,
        company_website_url=company_website_url,
        raw_company_description="Example builds tools.",
        founder_full_name="Ada Lovelace",
        founder_first_name="Ada",
        founder_last_name="Lovelace",
        founder_role_title="CTO",
        founder_linkedin_url=None,
        source_url=company_website_url,
        public_email_address=public_email_address,
        public_email_source_type=public_email_source_type,
    )


def build_enrichment_record(
    final_website_url: str = "https://example.com",
    canonical_company_domain: str = "example.com",
) -> DomainEnrichmentRecord:
    return DomainEnrichmentRecord(
        company_name="Example",
        raw_company_description="Example builds tools.",
        canonical_company_domain=canonical_company_domain,
        final_website_url=final_website_url,
        has_mx_records=False,
        mx_provider_name=None,
        enrichment_notes=("mx_skipped_offline",),
    )
