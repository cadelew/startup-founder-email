import json
from pathlib import Path

from startup_founder_email.jsonl_io import iter_jsonl_records
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.collect import (
    build_firecrawl_page_record,
    read_firecrawl_fixture_records,
    run_collection_stage,
)


def test_build_firecrawl_page_record_uses_expected_fields() -> None:
    firecrawl_payload = {
        "fetched_at_iso": "2026-05-05T20:00:00Z",
        "statusCode": 200,
        "markdown": "# Example",
        "html": None,
        "links": ["https://example.com/about", 42],
        "metadata": {"sourceURL": "https://example.com", "title": "Example"},
    }

    firecrawl_page_record = build_firecrawl_page_record(firecrawl_payload)

    assert firecrawl_page_record.url == "https://example.com"
    assert firecrawl_page_record.status_code == 200
    assert firecrawl_page_record.links == ("https://example.com/about",)
    assert firecrawl_page_record.metadata["title"] == "Example"


def test_build_firecrawl_page_record_defaults_missing_fetch_time_to_string() -> None:
    firecrawl_page_record = build_firecrawl_page_record(
        {"metadata": {"sourceURL": "https://example.com"}}
    )

    assert firecrawl_page_record.fetched_at_iso == ""


def test_read_firecrawl_fixture_records_sorts_fixture_files(tmp_path: Path) -> None:
    fixture_directory = tmp_path / "_fixtures"
    fixture_directory.mkdir()
    write_fixture(fixture_directory / "b.json", "https://b.example")
    write_fixture(fixture_directory / "a.json", "https://a.example")

    firecrawl_page_records = read_firecrawl_fixture_records(fixture_directory)

    assert [record.url for record in firecrawl_page_records] == [
        "https://a.example",
        "https://b.example",
    ]


def test_run_collection_stage_writes_raw_jsonl(tmp_path: Path) -> None:
    context = build_pipeline_context(tmp_path)
    fixture_directory = context.config.output_directories.raw_directory / "_fixtures"
    fixture_directory.mkdir()
    write_fixture(fixture_directory / "example.json", "https://example.com")

    exit_code = run_collection_stage(context)
    output_path = context.config.output_directories.raw_directory / "items.jsonl"

    assert exit_code == 0
    assert list(iter_jsonl_records(output_path)) == [
        {
            "fetched_at_iso": "2026-05-05T20:00:00Z",
            "html": "<html></html>",
            "links": [],
            "markdown": "# Example",
            "metadata": {"sourceURL": "https://example.com"},
            "status_code": 200,
            "url": "https://example.com",
        }
    ]


def write_fixture(fixture_path: Path, source_url: str) -> None:
    fixture_payload = {
        "fetched_at_iso": "2026-05-05T20:00:00Z",
        "statusCode": 200,
        "markdown": "# Example",
        "html": "<html></html>",
        "links": [],
        "metadata": {"sourceURL": source_url},
    }
    fixture_path.write_text(json.dumps(fixture_payload), encoding="utf-8")
