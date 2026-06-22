"""Configuration models and defaults for the pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from startup_founder_email.seeds import (
    read_startup_seeds_csv,
    startup_seeds_to_target_urls,
)


@dataclass(frozen=True)
class RequestTimingConfig:
    """Controls how politely the collector will space requests."""

    minimum_delay_seconds: float = 3.0
    maximum_delay_seconds: float = 8.0
    request_timeout_seconds: float = 20.0
    maximum_retry_attempts: int = 3


@dataclass(frozen=True)
class CollectorConfig:
    """Settings specific to source collection."""

    yc_companies_url: str = "https://www.ycombinator.com/companies"
    browser_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    )


_DEFAULT_CRAWL_INCLUDE_PATHS = (
    "team",
    "about",
    "leadership",
    "company",
    "people",
    "founders",
)
_DEFAULT_CRAWL_EXCLUDE_PATHS = (
    "blog",
    "careers",
    "jobs",
    "legal",
    "privacy",
    "terms",
)


@dataclass(frozen=True)
class FirecrawlConfig:
    """Settings for collecting pages through Firecrawl."""

    base_url: str = "http://localhost:3002"
    api_key_environment_variable: str = "FIRECRAWL_API_KEY"
    mode: str = "fixture"
    collection_mode: str = "scrape"
    target_urls: tuple[str, ...] = ()
    scrape_json_extract: bool = False
    llm_timeout_seconds: float | None = None
    crawl_limit: int = 20
    crawl_include_paths: tuple[str, ...] = _DEFAULT_CRAWL_INCLUDE_PATHS
    crawl_exclude_paths: tuple[str, ...] = _DEFAULT_CRAWL_EXCLUDE_PATHS
    crawl_poll_interval_seconds: float = 5.0
    crawl_timeout_seconds: float = 600.0
    seeds_csv_path: Path | None = None


@dataclass(frozen=True)
class EmailInferenceConfig:
    """Controls which inferred email patterns the generator tries."""

    email_patterns: tuple[str, ...] = (
        "{first}.{last}",
        "{first}{last}",
        "{f}{last}",
        "{f}.{last}",
        "{first}_{last}",
        "{first}",
        "{last}.{first}",
        "{last}{first}",
        "{last}{f}",
        "{last}",
        "{first}{l}",
        "{first}.{l}",
        "{f}{l}",
        "{f}.{l}",
    )


_DEFAULT_FREE_EMAIL_DOMAINS = (
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "hotmail.com",
    "hotmail.co.uk",
    "outlook.com",
    "live.com",
    "msn.com",
    "aol.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "mail.com",
    "protonmail.com",
    "proton.me",
    "zoho.com",
    "yandex.com",
    "gmx.com",
    "gmx.net",
    "fastmail.com",
    "tutanota.com",
    "tuta.io",
    "hey.com",
)


@dataclass(frozen=True)
class ValidationConfig:
    """Controls offline and optional live email validation checks."""

    enable_smtp_probe: bool = False
    enable_reacher_http_validation: bool = False
    enable_domain_a_record_check: bool = True
    reacher_base_url: str = "http://localhost:8080"
    reacher_timeout_seconds: float = 20.0
    domain_a_record_timeout_seconds: float = 3.0
    disposable_domains_path: Path | None = None
    free_email_domains: tuple[str, ...] = _DEFAULT_FREE_EMAIL_DOMAINS
    min_local_part_length: int = 3
    role_local_parts: tuple[str, ...] = (
        "admin",
        "contact",
        "hello",
        "help",
        "info",
        "sales",
        "support",
        "team",
    )


@dataclass(frozen=True)
class OutputDirectoryConfig:
    """Filesystem locations for stage outputs."""

    project_root: Path
    raw_directory: Path
    normalized_directory: Path
    enriched_directory: Path
    generated_directory: Path
    validated_directory: Path
    exported_directory: Path
    logs_directory: Path


@dataclass(frozen=True)
class PipelineConfig:
    """Shared application configuration."""

    request_timing: RequestTimingConfig
    collector: CollectorConfig
    firecrawl: FirecrawlConfig
    email_inference: EmailInferenceConfig
    validation: ValidationConfig
    output_directories: OutputDirectoryConfig


def build_output_directory_config(project_root: Path) -> OutputDirectoryConfig:
    """Build standard output paths relative to the repository root."""

    data_directory = project_root / "data"
    return OutputDirectoryConfig(
        project_root=project_root,
        raw_directory=data_directory / "raw",
        normalized_directory=data_directory / "normalized",
        enriched_directory=data_directory / "enriched",
        generated_directory=data_directory / "generated",
        validated_directory=data_directory / "validated",
        exported_directory=data_directory / "exported",
        logs_directory=data_directory / "logs",
    )


def build_job_output_directory_config(project_root: Path, job_id: str) -> OutputDirectoryConfig:
    """Build output paths scoped to one API job."""

    job_data_directory = project_root / "data" / "jobs" / job_id
    return OutputDirectoryConfig(
        project_root=project_root,
        raw_directory=job_data_directory / "raw",
        normalized_directory=job_data_directory / "normalized",
        enriched_directory=job_data_directory / "enriched",
        generated_directory=job_data_directory / "generated",
        validated_directory=job_data_directory / "validated",
        exported_directory=job_data_directory / "exported",
        logs_directory=job_data_directory / "logs",
    )


def load_pipeline_config(project_root: Path) -> PipelineConfig:
    """Load the application's configuration.

    Phase 1 uses code-based defaults to keep the project simple and readable.
    Future phases can add environment variables or config files if needed.
    """

    collector_config = CollectorConfig()
    project_root = project_root.resolve()
    seeds_csv_path = read_optional_path_environment_variable(
        project_root,
        "STARTUP_FOUNDER_EMAIL_SEEDS_CSV",
    )
    target_urls = resolve_firecrawl_target_urls(
        project_root=project_root,
        seeds_csv_path=seeds_csv_path,
        raw_target_urls=os.environ.get("STARTUP_FOUNDER_EMAIL_FIRECRAWL_URLS"),
        default_target_url=collector_config.yc_companies_url,
    )
    return PipelineConfig(
        request_timing=RequestTimingConfig(),
        collector=collector_config,
        firecrawl=FirecrawlConfig(
            base_url=os.environ.get("FIRECRAWL_BASE_URL", "http://localhost:3002"),
            mode=os.environ.get("STARTUP_FOUNDER_EMAIL_FIRECRAWL_MODE", "fixture"),
            collection_mode=os.environ.get(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_COLLECTION_MODE",
                "scrape",
            ).strip().lower(),
            target_urls=target_urls,
            scrape_json_extract=read_truthy_environment_variable(
                os.environ.get("STARTUP_FOUNDER_EMAIL_FIRECRAWL_JSON_EXTRACT")
            ),
            llm_timeout_seconds=read_optional_float_environment_variable(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_LLM_TIMEOUT_SECONDS"
            ),
            crawl_limit=read_optional_int_environment_variable(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_CRAWL_LIMIT"
            )
            or 20,
            crawl_include_paths=read_comma_separated_environment_variable(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_CRAWL_INCLUDE_PATHS",
                _DEFAULT_CRAWL_INCLUDE_PATHS,
            ),
            crawl_exclude_paths=read_comma_separated_environment_variable(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_CRAWL_EXCLUDE_PATHS",
                _DEFAULT_CRAWL_EXCLUDE_PATHS,
            ),
            crawl_poll_interval_seconds=read_optional_float_environment_variable(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_CRAWL_POLL_INTERVAL_SECONDS"
            )
            or 5.0,
            crawl_timeout_seconds=read_optional_float_environment_variable(
                "STARTUP_FOUNDER_EMAIL_FIRECRAWL_CRAWL_TIMEOUT_SECONDS"
            )
            or 600.0,
            seeds_csv_path=seeds_csv_path,
        ),
        email_inference=EmailInferenceConfig(),
        validation=ValidationConfig(
            enable_reacher_http_validation=read_truthy_environment_variable(
                os.environ.get("STARTUP_FOUNDER_EMAIL_REACHER_ENABLE")
            ),
            reacher_base_url=os.environ.get(
                "STARTUP_FOUNDER_EMAIL_REACHER_BASE_URL",
                "http://localhost:8080",
            ),
            reacher_timeout_seconds=read_optional_float_environment_variable(
                "STARTUP_FOUNDER_EMAIL_REACHER_TIMEOUT_SECONDS"
            )
            or 20.0,
            disposable_domains_path=project_root
            / "data"
            / "validated"
            / "_disposable_domains.txt"
        ),
        output_directories=build_output_directory_config(project_root),
    )


def read_truthy_environment_variable(raw_value: str | None) -> bool:
    """Return True for common affirmative environment variable spellings."""

    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def read_optional_float_environment_variable(raw_key: str) -> float | None:
    """Parse a positive float from ``os.environ[raw_key]`` when set."""

    raw_value = os.environ.get(raw_key)
    if raw_value is None or not str(raw_value).strip():
        return None
    try:
        parsed = float(raw_value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def read_firecrawl_target_urls(
    raw_target_urls: str | None,
    default_target_url: str,
) -> tuple[str, ...]:
    """Read comma-separated Firecrawl target URLs from the environment."""

    if raw_target_urls is None:
        return (default_target_url,)

    target_urls = tuple(
        target_url.strip()
        for target_url in raw_target_urls.split(",")
        if target_url.strip()
    )
    return target_urls or (default_target_url,)


def resolve_firecrawl_target_urls(
    *,
    project_root: Path,
    seeds_csv_path: Path | None,
    raw_target_urls: str | None,
    default_target_url: str,
) -> tuple[str, ...]:
    """Resolve crawl/scrape seeds from CSV and/or environment variables."""

    if seeds_csv_path is not None:
        seeds = read_startup_seeds_csv(seeds_csv_path)
        if seeds:
            return startup_seeds_to_target_urls(seeds)

    return read_firecrawl_target_urls(raw_target_urls, default_target_url)


def read_optional_path_environment_variable(
    project_root: Path,
    environment_key: str,
) -> Path | None:
    """Read a filesystem path from the environment, resolving relative paths."""

    raw_value = os.environ.get(environment_key)
    if raw_value is None or not raw_value.strip():
        return None
    path = Path(raw_value.strip())
    if not path.is_absolute():
        path = project_root / path
    return path


def read_optional_int_environment_variable(environment_key: str) -> int | None:
    """Parse a positive integer from the environment when set."""

    raw_value = os.environ.get(environment_key)
    if raw_value is None or not raw_value.strip():
        return None
    try:
        parsed = int(raw_value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def read_comma_separated_environment_variable(
    environment_key: str,
    default_values: tuple[str, ...],
) -> tuple[str, ...]:
    """Read comma-separated tokens or return defaults when unset."""

    raw_value = os.environ.get(environment_key)
    if raw_value is None or not raw_value.strip():
        return default_values
    values = tuple(
        token.strip() for token in raw_value.split(",") if token.strip()
    )
    return values or default_values
