"""Build pipeline configuration for API jobs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from startup_founder_email.config import (
    FirecrawlConfig,
    PipelineConfig,
    build_job_output_directory_config,
    load_pipeline_config,
)


def build_job_pipeline_config(
    project_root: Path,
    *,
    job_id: str,
    seed_urls: tuple[str, ...],
    collection_mode: str = "crawl",
    firecrawl_mode: str = "live",
    scrape_json_extract: bool | None = None,
) -> PipelineConfig:
    """Return pipeline config for one API-driven collect job."""

    pipeline_config = load_pipeline_config(project_root)
    firecrawl_config = pipeline_config.firecrawl
    firecrawl_updates: dict[str, object] = {
        "mode": firecrawl_mode,
        "collection_mode": collection_mode,
        "target_urls": seed_urls,
    }
    if scrape_json_extract is not None:
        firecrawl_updates["scrape_json_extract"] = scrape_json_extract
    updated_firecrawl_config = replace(firecrawl_config, **firecrawl_updates)
    return replace(
        pipeline_config,
        firecrawl=updated_firecrawl_config,
        output_directories=build_job_output_directory_config(
            pipeline_config.output_directories.project_root,
            job_id,
        ),
    )
