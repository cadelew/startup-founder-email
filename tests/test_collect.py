import json
from pathlib import Path

from startup_founder_email.jsonl_io import iter_jsonl_records
from startup_founder_email.pipeline import build_pipeline_context
from startup_founder_email.stages.collect import (
    build_firecrawl_crawl_request_body,
    build_firecrawl_scrape_request_body,
    build_firecrawl_page_record,
    collect_live_firecrawl_crawl_records,
    collect_live_firecrawl_page_records,
    crawl_results_to_page_records,
    merge_firecrawl_json_extraction_payload,
    poll_firecrawl_crawl_until_complete,
    should_request_llm_extraction,
    read_firecrawl_data_payload,
    read_firecrawl_fixture_records,
    run_collection_stage,
)
from startup_founder_email.config import FirecrawlConfig


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


def test_build_firecrawl_page_record_reads_status_code_from_metadata() -> None:
    firecrawl_page_record = build_firecrawl_page_record(
        {
            "markdown": "# Example",
            "metadata": {
                "sourceURL": "https://example.com",
                "statusCode": 201,
            },
        }
    )

    assert firecrawl_page_record.status_code == 201


def test_build_firecrawl_page_record_defaults_missing_fetch_time_to_string() -> None:
    firecrawl_page_record = build_firecrawl_page_record(
        {"metadata": {"sourceURL": "https://example.com"}}
    )

    assert firecrawl_page_record.fetched_at_iso == ""


def test_read_firecrawl_data_payload_returns_scrape_data() -> None:
    data_payload = {
        "markdown": "# Example",
        "metadata": {"sourceURL": "https://example.com"},
    }

    assert read_firecrawl_data_payload({"success": True, "data": data_payload}) == data_payload


def test_build_firecrawl_scrape_request_body_adds_json_when_json_extract_enabled() -> None:
    firecrawl_config = FirecrawlConfig(mode="live", scrape_json_extract=True)
    body = build_firecrawl_scrape_request_body(firecrawl_config, "https://example.com/team")

    assert body["url"] == "https://example.com/team"
    assert "json" in body["formats"]
    assert "schema" in body["jsonOptions"]
    assert "prompt" in body["jsonOptions"]


def test_build_firecrawl_scrape_request_body_can_force_markdown_only() -> None:
    firecrawl_config = FirecrawlConfig(mode="live", scrape_json_extract=True)
    body = build_firecrawl_scrape_request_body(
        firecrawl_config,
        "https://example.com/team",
        include_json_extract=False,
    )

    assert body["formats"] == ["markdown", "html", "links"]
    assert "jsonOptions" not in body


def test_should_request_llm_extraction_skips_founder_role_pages() -> None:
    payload = {
        "markdown": (
            "OUR FOUNDERS\n------------\n\n"
            "Example was founded by operators building workflow tools.\n\n"
            "Ada Lovelace\n\n"
            "Founder, CEO\n"
        )
    }

    should_request_json, reasons = should_request_llm_extraction(payload)

    assert should_request_json is False
    assert reasons == ()


def test_should_request_llm_extraction_flags_missing_founders() -> None:
    payload = {
        "markdown": "# Example\n\nExample builds workflow tools for robotics teams."
    }

    should_request_json, reasons = should_request_llm_extraction(payload)

    assert should_request_json is True
    assert "founder_signal_not_found" in reasons


def test_merge_firecrawl_json_extraction_payload_copies_structured_fields() -> None:
    base_payload = {"markdown": "# Example", "metadata": {"sourceURL": "https://example.com"}}
    json_payload = {"json": {"founders": [{"full_name": "Ada Lovelace"}]}, "warning": None}

    merge_firecrawl_json_extraction_payload(base_payload, json_payload)

    assert base_payload["json"] == {"founders": [{"full_name": "Ada Lovelace"}]}
    assert base_payload["warning"] is None


def test_collect_live_firecrawl_page_records_scrapes_configured_urls(monkeypatch) -> None:
    scraped_urls: list[str] = []

    def fake_post_firecrawl_scrape_request(
        firecrawl_config: FirecrawlConfig,
        target_url: str,
        request_timeout_seconds: float,
        *,
        include_json_extract: bool | None = None,
    ) -> dict[str, object]:
        scraped_urls.append(target_url)
        return {
            "success": True,
            "data": {
                "fetched_at_iso": "2026-05-09T18:00:00Z",
                "markdown": "# Example",
                "metadata": {
                    "sourceURL": target_url,
                    "statusCode": 200,
                },
                "links": ["https://example.com/about"],
            },
        }

    monkeypatch.setattr(
        "startup_founder_email.stages.collect.post_firecrawl_scrape_request",
        fake_post_firecrawl_scrape_request,
    )
    firecrawl_config = FirecrawlConfig(
        mode="live",
        target_urls=("https://a.example", "https://b.example"),
    )

    firecrawl_page_records = collect_live_firecrawl_page_records(firecrawl_config, 20.0)

    assert scraped_urls == ["https://a.example", "https://b.example"]
    assert [record.url for record in firecrawl_page_records] == [
        "https://a.example",
        "https://b.example",
    ]
    assert firecrawl_page_records[0].links == ("https://example.com/about",)


def test_collect_live_firecrawl_page_records_skips_json_when_founders_found(monkeypatch) -> None:
    include_json_values: list[bool | None] = []

    def fake_post_firecrawl_scrape_request(
        firecrawl_config: FirecrawlConfig,
        target_url: str,
        request_timeout_seconds: float,
        *,
        include_json_extract: bool | None = None,
    ) -> dict[str, object]:
        include_json_values.append(include_json_extract)
        return {
            "success": True,
            "data": {
                "fetched_at_iso": "2026-05-09T18:00:00Z",
                "markdown": "Ada Lovelace\n\nFounder, CEO\n",
                "metadata": {"sourceURL": target_url, "statusCode": 200},
            },
        }

    monkeypatch.setattr(
        "startup_founder_email.stages.collect.post_firecrawl_scrape_request",
        fake_post_firecrawl_scrape_request,
    )
    firecrawl_config = FirecrawlConfig(
        mode="live",
        target_urls=("https://example.com/team",),
        scrape_json_extract=True,
    )

    firecrawl_page_records = collect_live_firecrawl_page_records(firecrawl_config, 20.0)

    assert include_json_values == [False]
    assert firecrawl_page_records[0].llm_extraction is None


def test_collect_live_firecrawl_page_records_falls_back_to_json(monkeypatch) -> None:
    include_json_values: list[bool | None] = []

    def fake_post_firecrawl_scrape_request(
        firecrawl_config: FirecrawlConfig,
        target_url: str,
        request_timeout_seconds: float,
        *,
        include_json_extract: bool | None = None,
    ) -> dict[str, object]:
        include_json_values.append(include_json_extract)
        if include_json_extract:
            return {
                "success": True,
                "data": {
                    "json": {
                        "company_name": "Example",
                        "founders": [{"full_name": "Ada Lovelace"}],
                    },
                    "metadata": {"sourceURL": target_url, "statusCode": 200},
                },
            }
        return {
            "success": True,
            "data": {
                "fetched_at_iso": "2026-05-09T18:00:00Z",
                "markdown": "# Example\n\nExample builds workflow tools.",
                "metadata": {"sourceURL": target_url, "statusCode": 200},
            },
        }

    monkeypatch.setattr(
        "startup_founder_email.stages.collect.post_firecrawl_scrape_request",
        fake_post_firecrawl_scrape_request,
    )
    firecrawl_config = FirecrawlConfig(
        mode="live",
        target_urls=("https://example.com/about",),
        scrape_json_extract=True,
    )

    firecrawl_page_records = collect_live_firecrawl_page_records(firecrawl_config, 20.0)

    assert include_json_values == [False, True]
    assert firecrawl_page_records[0].markdown == "# Example\n\nExample builds workflow tools."
    assert firecrawl_page_records[0].llm_extraction == {
        "company_name": "Example",
        "founders": [{"full_name": "Ada Lovelace"}],
    }


def test_build_firecrawl_crawl_request_body_includes_path_filters() -> None:
    firecrawl_config = FirecrawlConfig(
        mode="live",
        collection_mode="crawl",
        crawl_limit=12,
        crawl_include_paths=("team", "about"),
        crawl_exclude_paths=("blog",),
    )

    body = build_firecrawl_crawl_request_body(firecrawl_config, "https://example.com")

    assert body["url"] == "https://example.com"
    assert body["limit"] == 12
    assert body["includePaths"] == ["team", "about"]
    assert body["excludePaths"] == ["blog"]
    assert body["scrapeOptions"]["formats"] == ["markdown", "html", "links"]


def test_crawl_results_to_page_records_sets_seed_metadata() -> None:
    page_records = crawl_results_to_page_records(
        seed_url="https://example.com",
        crawl_id="crawl-123",
        page_payloads=[
            {
                "markdown": "# Team",
                "metadata": {"sourceURL": "https://example.com/team"},
            }
        ],
        fetched_at_iso="2026-05-05T20:00:00Z",
    )

    assert len(page_records) == 1
    assert page_records[0].url == "https://example.com/team"
    assert page_records[0].seed_url == "https://example.com"
    assert page_records[0].crawl_id == "crawl-123"


def test_collect_live_firecrawl_crawl_records_polls_crawl_jobs(monkeypatch) -> None:
    crawl_calls: list[str] = []

    def fake_post_firecrawl_crawl_request(
        firecrawl_config: FirecrawlConfig,
        seed_url: str,
        request_timeout_seconds: float,
    ) -> dict[str, object]:
        crawl_calls.append(seed_url)
        return {"success": True, "id": f"id-for-{seed_url}"}

    def fake_poll_firecrawl_crawl_until_complete(
        firecrawl_config: FirecrawlConfig,
        crawl_id: str,
        crawl_timeout_seconds: float,
    ) -> list[dict[str, object]]:
        return [
            {
                "markdown": "# Team",
                "metadata": {"sourceURL": f"{crawl_id}/team"},
            }
        ]

    monkeypatch.setattr(
        "startup_founder_email.stages.collect.post_firecrawl_crawl_request",
        fake_post_firecrawl_crawl_request,
    )
    monkeypatch.setattr(
        "startup_founder_email.stages.collect.poll_firecrawl_crawl_until_complete",
        fake_poll_firecrawl_crawl_until_complete,
    )

    firecrawl_config = FirecrawlConfig(
        mode="live",
        collection_mode="crawl",
        target_urls=("https://a.example", "https://b.example"),
    )
    page_records = collect_live_firecrawl_crawl_records(firecrawl_config, 30.0)

    assert crawl_calls == ["https://a.example", "https://b.example"]
    assert len(page_records) == 2
    assert {record.seed_url for record in page_records} == {
        "https://a.example",
        "https://b.example",
    }


def test_collect_live_firecrawl_page_records_uses_crawl_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        "startup_founder_email.stages.collect.collect_live_firecrawl_crawl_records",
        lambda firecrawl_config, request_timeout_seconds: [],
    )

    firecrawl_config = FirecrawlConfig(mode="live", collection_mode="crawl")
    page_records = collect_live_firecrawl_page_records(firecrawl_config, 20.0)

    assert page_records == []


def test_poll_firecrawl_crawl_until_complete_waits_for_completed_status(monkeypatch) -> None:
    responses = [
        {"status": "scraping", "completed": 0, "total": 2},
        {
            "status": "completed",
            "data": [{"markdown": "# About", "metadata": {"sourceURL": "https://example.com/about"}}],
        },
    ]

    def fake_get_firecrawl_crawl_status(
        firecrawl_config: FirecrawlConfig,
        crawl_id: str,
        request_timeout_seconds: float,
    ) -> dict[str, object]:
        return responses.pop(0)

    monkeypatch.setattr(
        "startup_founder_email.stages.collect.get_firecrawl_crawl_status",
        fake_get_firecrawl_crawl_status,
    )
    monkeypatch.setattr("startup_founder_email.stages.collect.time.sleep", lambda _: None)

    pages = poll_firecrawl_crawl_until_complete(
        FirecrawlConfig(mode="live"),
        "job-1",
        60.0,
    )

    assert len(pages) == 1
    assert pages[0]["metadata"]["sourceURL"] == "https://example.com/about"


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
    records = list(iter_jsonl_records(output_path))
    assert len(records) == 1
    assert records[0]["url"] == "https://example.com"
    assert records[0]["seed_url"] is None
    assert records[0]["crawl_id"] is None


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
