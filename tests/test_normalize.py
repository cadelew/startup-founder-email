from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records
from startup_founder_email.models import FirecrawlPageRecord
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.normalize import (
    classify_public_email_source_type,
    extract_founder_segments,
    extract_public_email_address,
    normalize_raw_page_record,
    run_normalization_stage,
)


def test_extract_founder_segments_reads_founders_line() -> None:
    page_text = "Founders: Ada Lovelace, CTO and Charles Babbage, CEO"

    assert extract_founder_segments(page_text) == [
        "Ada Lovelace, CTO",
        "Charles Babbage, CEO",
    ]


def test_extract_founder_segments_reads_team_page_founder_roles() -> None:
    page_text = """# Our Team

OUR FOUNDERS
------------

![Federico Chávez-Torres](https://texsoftware.com/team/fed-headshot-smile.webp)

Federico Chávez-Torres

Founder, CEO

![Matthew Bennett](https://texsoftware.com/team/matt-smiling.webp)

Matthew Bennett

Founder, COO
"""

    assert extract_founder_segments(page_text) == [
        "Federico Chávez-Torres, Founder, CEO",
        "Matthew Bennett, Founder, COO",
    ]


def test_extract_public_email_address_prefers_mailto_links() -> None:
    email_address = extract_public_email_address(
        "Contact us at text@example.com.",
        ("mailto:hello@example.com",),
    )

    assert email_address == "hello@example.com"


def test_classify_public_email_source_type_marks_page_email_as_company_level() -> None:
    assert classify_public_email_source_type("hello@example.com") == "company"
    assert classify_public_email_source_type(None) == ""


def test_normalize_raw_page_record_builds_founder_rows() -> None:
    raw_page_record = FirecrawlPageRecord(
        url="https://analytical-engines.example",
        fetched_at_iso="2026-05-05T20:00:00Z",
        status_code=200,
        markdown=(
            "# Analytical Engines\n\n"
            "Analytical Engines builds workflow tools.\n\n"
            "Founders: Ada Lovelace, CTO and Charles Babbage, CEO"
        ),
        html=None,
    )

    normalized_founder_records = normalize_raw_page_record(raw_page_record)

    assert [record.founder_full_name for record in normalized_founder_records] == [
        "Ada Lovelace",
        "Charles Babbage",
    ]
    assert normalized_founder_records[0].company_name == "Analytical Engines"
    assert normalized_founder_records[0].founder_role_title == "CTO"
    assert normalized_founder_records[0].public_email_source_type == ""


def test_normalize_raw_page_record_reads_marketing_team_page() -> None:
    raw_page_record = FirecrawlPageRecord(
        url="https://texsoftware.com/team",
        fetched_at_iso="2026-05-09T21:27:50Z",
        status_code=200,
        markdown=(
            "[Home](https://texsoftware.com/)\nOur Team\n\n"
            "Our Team\n========\n\nMeet the founders.\n\n"
            "OUR FOUNDERS\n------------\n\n"
            "Tex was founded by operators.\n\n"
            "![Federico Chávez-Torres](https://texsoftware.com/team/f.webp)\n\n"
            "Federico Chávez-Torres\n\nFounder, CEO\n\n"
            "![Matthew Bennett](https://texsoftware.com/team/m.webp)\n\n"
            "Matthew Bennett\n\nFounder, COO\n"
        ),
        html=None,
        metadata={"title": "Team - Tex Software"},
    )

    normalized_founder_records = normalize_raw_page_record(raw_page_record)

    assert len(normalized_founder_records) == 2
    assert normalized_founder_records[0].founder_full_name == "Federico Chávez-Torres"
    assert normalized_founder_records[0].founder_role_title == "Founder, CEO"
    assert normalized_founder_records[1].founder_full_name == "Matthew Bennett"
    assert normalized_founder_records[1].founder_role_title == "Founder, COO"
    assert all(not record.cleaning_notes for record in normalized_founder_records)
    assert normalized_founder_records[0].company_name == "Tex Software"
    assert (
        normalized_founder_records[0].raw_company_description
        == "Tex was founded by operators."
    )


def test_normalize_prefers_firecrawl_llm_extraction_when_present() -> None:
    raw_page_record = FirecrawlPageRecord(
        url="https://example.com/about",
        fetched_at_iso="2026-05-10T12:00:00Z",
        status_code=200,
        markdown="# Site\n\nFounders: Wrong Person, CEO",
        html=None,
        metadata={"title": "About - Ignored Title"},
        llm_extraction={
            "company_name": "ExampleCo",
            "company_description": "Builds workflow robots.",
            "founders": [
                {
                    "full_name": "Ada Lovelace",
                    "role_title": "CTO",
                    "email": "ada@example.com",
                    "linkedin_url": "https://linkedin.com/in/ada",
                },
            ],
        },
    )

    normalized_founder_records = normalize_raw_page_record(raw_page_record)

    assert len(normalized_founder_records) == 1
    assert normalized_founder_records[0].founder_full_name == "Ada Lovelace"
    assert normalized_founder_records[0].founder_role_title == "CTO"
    assert normalized_founder_records[0].company_name == "ExampleCo"
    assert normalized_founder_records[0].raw_company_description == "Builds workflow robots."
    assert normalized_founder_records[0].public_email_address == "ada@example.com"
    assert normalized_founder_records[0].public_email_source_type == "person"
    assert normalized_founder_records[0].founder_linkedin_url == "https://linkedin.com/in/ada"
    assert normalized_founder_records[0].cleaning_notes == ("founder_source_firecrawl_json",)


def test_normalize_prefers_og_site_name_over_generic_heading() -> None:
    raw_page_record = FirecrawlPageRecord(
        url="https://acme.example/team",
        fetched_at_iso="2026-05-09T22:00:00Z",
        status_code=200,
        markdown="# Our Team\n\nFounders: Jane Doe, CEO\n",
        html=None,
        metadata={"og:site_name": "Acme Robotics", "title": "Team - Acme Robotics"},
    )

    normalized_founder_records = normalize_raw_page_record(raw_page_record)

    assert normalized_founder_records[0].company_name == "Acme Robotics"


def test_normalize_uses_metadata_description_when_body_is_mostly_nav() -> None:
    raw_page_record = FirecrawlPageRecord(
        url="https://exampleco.example/",
        fetched_at_iso="2026-05-09T22:05:00Z",
        status_code=200,
        markdown="[Home](https://exampleco.example)\n\nHi.",
        html=None,
        metadata={
            "title": "ExampleCo",
            "description": "ExampleCo builds autonomous forklifts for warehouse logistics.",
        },
    )

    normalized_founder_records = normalize_raw_page_record(raw_page_record)

    assert normalized_founder_records[0].cleaning_notes == ("founder_not_found",)
    assert normalized_founder_records[0].company_name == "ExampleCo"
    assert (
        normalized_founder_records[0].raw_company_description
        == "ExampleCo builds autonomous forklifts for warehouse logistics."
    )


def test_run_normalization_stage_writes_normalized_jsonl(tmp_path) -> None:
    context = build_pipeline_context(tmp_path)
    raw_path = context.config.output_directories.raw_directory / "items.jsonl"
    write_jsonl_records(
        raw_path,
        [
            FirecrawlPageRecord(
                url="https://robotics-labs.example",
                fetched_at_iso="2026-05-05T20:05:00Z",
                status_code=200,
                markdown=(
                    "# Robotics Labs\n\n"
                    "Robotics Labs helps warehouse teams.\n\n"
                    "Founders: Grace Hopper, CEO"
                ),
                html=None,
            )
        ],
    )

    exit_code = run_normalization_stage(context)
    output_path = context.config.output_directories.normalized_directory / "items.jsonl"
    normalized_records = list(iter_jsonl_records(output_path))

    assert exit_code == 0
    assert normalized_records[0]["company_name"] == "Robotics Labs"
    assert normalized_records[0]["founder_full_name"] == "Grace Hopper"
    assert normalized_records[0]["public_email_source_type"] == ""
