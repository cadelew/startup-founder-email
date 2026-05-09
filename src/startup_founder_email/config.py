"""Configuration models and defaults for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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


@dataclass(frozen=True)
class FirecrawlConfig:
    """Settings for collecting pages through Firecrawl."""

    base_url: str = "http://localhost:3002"
    api_key_environment_variable: str = "FIRECRAWL_API_KEY"
    mode: str = "fixture"


@dataclass(frozen=True)
class EmailInferenceConfig:
    """Controls which inferred email patterns the generator tries."""

    email_patterns: tuple[str, ...] = (
        "{first}.{last}",
        "{first}{last}",
        "{f}{last}",
        "{first}",
        "{last}",
        "{first}{l}",
        "{first}.{l}",
    )


@dataclass(frozen=True)
class ValidationConfig:
    """Controls offline and optional live email validation checks."""

    enable_smtp_probe: bool = False
    disposable_domains_path: Path | None = None
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


def load_pipeline_config(project_root: Path) -> PipelineConfig:
    """Load the application's configuration.

    Phase 1 uses code-based defaults to keep the project simple and readable.
    Future phases can add environment variables or config files if needed.
    """

    return PipelineConfig(
        request_timing=RequestTimingConfig(),
        collector=CollectorConfig(),
        firecrawl=FirecrawlConfig(),
        email_inference=EmailInferenceConfig(),
        validation=ValidationConfig(
            disposable_domains_path=project_root
            / "data"
            / "validated"
            / "_disposable_domains.txt"
        ),
        output_directories=build_output_directory_config(project_root),
    )
