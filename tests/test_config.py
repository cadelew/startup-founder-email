from pathlib import Path

from startup_founder_email.config import (
    load_pipeline_config,
    read_firecrawl_target_urls,
    read_optional_float_environment_variable,
    read_truthy_environment_variable,
)


def test_load_pipeline_config_builds_expected_output_directories() -> None:
    project_root = Path("/tmp/example-project")

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


def test_read_firecrawl_target_urls_falls_back_to_default_url() -> None:
    assert read_firecrawl_target_urls(None, "https://default.example") == (
        "https://default.example",
    )
    assert read_firecrawl_target_urls(" , ", "https://default.example") == (
        "https://default.example",
    )
