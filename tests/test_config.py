from pathlib import Path

from startup_founder_email.config import (
    build_job_output_directory_config,
    load_pipeline_config,
    read_firecrawl_target_urls,
    read_optional_float_environment_variable,
    read_truthy_environment_variable,
)


def test_load_pipeline_config_builds_expected_output_directories() -> None:
    project_root = Path("/tmp/example-project").resolve()

    pipeline_config = load_pipeline_config(project_root)

    assert pipeline_config.output_directories.raw_directory == project_root / "data" / "raw"
    assert (
        pipeline_config.output_directories.validated_directory
        == project_root / "data" / "validated"
    )
    assert pipeline_config.output_directories.logs_directory == project_root / "data" / "logs"
    assert pipeline_config.request_timing.minimum_delay_seconds == 3.0
    assert pipeline_config.firecrawl.mode == "fixture"
    assert pipeline_config.email_inference.email_patterns[0] == "{first}.{last}"
    assert pipeline_config.validation.enable_smtp_probe is False
    assert pipeline_config.validation.enable_reacher_http_validation is False
    assert pipeline_config.validation.reacher_base_url == "http://localhost:8080"
    assert pipeline_config.validation.reacher_timeout_seconds == 20.0


def test_build_job_output_directory_config_scopes_outputs_to_job_id() -> None:
    project_root = Path("/tmp/example-project").resolve()

    output_directories = build_job_output_directory_config(project_root, "job-123")

    assert output_directories.raw_directory == project_root / "data" / "jobs" / "job-123" / "raw"
    assert (
        output_directories.exported_directory
        == project_root / "data" / "jobs" / "job-123" / "exported"
    )
    assert output_directories.logs_directory == project_root / "data" / "jobs" / "job-123" / "logs"


def test_load_pipeline_config_reads_firecrawl_json_extract_environment(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_FIRECRAWL_JSON_EXTRACT", "true")
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_FIRECRAWL_LLM_TIMEOUT_SECONDS", "180")

    pipeline_config = load_pipeline_config(Path("/tmp/example-project"))

    assert pipeline_config.firecrawl.scrape_json_extract is True
    assert pipeline_config.firecrawl.llm_timeout_seconds == 180.0


def test_read_truthy_environment_variable_accepts_common_true_spellings() -> None:
    assert read_truthy_environment_variable(None) is False
    assert read_truthy_environment_variable("") is False
    assert read_truthy_environment_variable("TRUE") is True
    assert read_truthy_environment_variable("1") is True


def test_read_optional_float_environment_variable(monkeypatch) -> None:
    assert read_optional_float_environment_variable("STARTUP_FOUNDER_EMAIL_UNIT_TEST_FLOAT") is None
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_UNIT_TEST_FLOAT", "42")
    assert read_optional_float_environment_variable("STARTUP_FOUNDER_EMAIL_UNIT_TEST_FLOAT") == 42.0


def test_load_pipeline_config_reads_live_firecrawl_environment(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_FIRECRAWL_MODE", "live")
    monkeypatch.setenv("FIRECRAWL_BASE_URL", "http://localhost:3002")
    monkeypatch.setenv(
        "STARTUP_FOUNDER_EMAIL_FIRECRAWL_URLS",
        "https://a.example, https://b.example",
    )

    pipeline_config = load_pipeline_config(Path("/tmp/example-project"))

    assert pipeline_config.firecrawl.mode == "live"
    assert pipeline_config.firecrawl.base_url == "http://localhost:3002"
    assert pipeline_config.firecrawl.target_urls == (
        "https://a.example",
        "https://b.example",
    )


def test_load_pipeline_config_reads_reacher_validation_environment(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_REACHER_ENABLE", "true")
    monkeypatch.setenv(
        "STARTUP_FOUNDER_EMAIL_REACHER_BASE_URL",
        "http://localhost:18080",
    )
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_REACHER_TIMEOUT_SECONDS", "45")

    pipeline_config = load_pipeline_config(Path("/tmp/example-project"))

    assert pipeline_config.validation.enable_reacher_http_validation is True
    assert pipeline_config.validation.reacher_base_url == "http://localhost:18080"
    assert pipeline_config.validation.reacher_timeout_seconds == 45.0


def test_load_pipeline_config_reads_crawl_collection_mode(monkeypatch) -> None:
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_FIRECRAWL_COLLECTION_MODE", "crawl")
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_FIRECRAWL_CRAWL_LIMIT", "15")

    pipeline_config = load_pipeline_config(Path("/tmp/example-project"))

    assert pipeline_config.firecrawl.collection_mode == "crawl"
    assert pipeline_config.firecrawl.crawl_limit == 15


def test_load_pipeline_config_reads_seeds_csv(tmp_path, monkeypatch) -> None:
    seeds_csv_path = tmp_path / "data" / "seeds" / "startup_urls.csv"
    seeds_csv_path.parent.mkdir(parents=True)
    seeds_csv_path.write_text(
        "company_name,website_url\nExample,https://example.com\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STARTUP_FOUNDER_EMAIL_SEEDS_CSV", "data/seeds/startup_urls.csv")

    pipeline_config = load_pipeline_config(tmp_path)

    assert pipeline_config.firecrawl.seeds_csv_path == seeds_csv_path
    assert pipeline_config.firecrawl.target_urls == ("https://example.com",)


def test_read_firecrawl_target_urls_falls_back_to_default_url() -> None:
    assert read_firecrawl_target_urls(None, "https://default.example") == (
        "https://default.example",
    )
    assert read_firecrawl_target_urls(" , ", "https://default.example") == (
        "https://default.example",
    )
