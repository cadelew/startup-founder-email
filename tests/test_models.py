from startup_founder_email.models import (
    ContactCandidateRecord,
    FirecrawlPageRecord,
    RawCompanyRecord,
)


def test_raw_company_record_keeps_source_payload() -> None:
    raw_company_record = RawCompanyRecord(
        source_name="yc-companies",
        source_url="https://example.com",
        fetched_at_iso="2026-04-28T18:00:00Z",
        raw_company_description="Software for robotics teams.",
        payload={"company_name": "Example"},
    )

    assert raw_company_record.payload["company_name"] == "Example"
    assert raw_company_record.raw_company_description == "Software for robotics teams."


def test_firecrawl_page_record_defaults_optional_collections() -> None:
    firecrawl_page_record = FirecrawlPageRecord(
        url="https://example.com",
        fetched_at_iso="2026-05-05T20:00:00Z",
        status_code=200,
        markdown="Contact us at hello@example.com.",
        html=None,
    )

    assert firecrawl_page_record.links == ()
    assert firecrawl_page_record.metadata == {}


def test_contact_candidate_record_defaults_tracking_fields() -> None:
    contact_candidate_record = ContactCandidateRecord(
        founder_full_name="Ada Lovelace",
        company_name="Analytical Engines",
        batch_name="S24",
        industry_name="Developer Tools",
        company_website_url="https://example.com",
        raw_company_description="Build tools for faster scientific computing.",
        company_summary="Builds tools that make scientific computing faster.",
        canonical_company_domain="example.com",
        public_email_address=None,
        public_email_source_type="",
        best_email_guess="ada@example.com",
        alternative_email_guess="ada.lovelace@example.com",
        email_source_type="inferred",
        email_confidence_level="medium",
        mx_provider_name="Google Workspace",
        founder_linkedin_url=None,
        source_url="https://example.com/company",
    )

    assert contact_candidate_record.status == ""
    assert contact_candidate_record.notes == ""
    assert contact_candidate_record.company_summary is not None
    assert contact_candidate_record.smtp_probe_status == "skipped"
    assert contact_candidate_record.validation_notes == ()
