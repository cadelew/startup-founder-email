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
