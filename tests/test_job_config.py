from pathlib import Path

from startup_founder_email.job_config import build_job_pipeline_config


def test_build_job_pipeline_config_scopes_output_directories_to_job_id() -> None:
    project_root = Path("/tmp/example-project").resolve()

    pipeline_config = build_job_pipeline_config(
        project_root,
        job_id="job-123",
        seed_urls=("https://example.com",),
    )

    assert pipeline_config.firecrawl.mode == "live"
    assert pipeline_config.firecrawl.target_urls == ("https://example.com",)
    assert (
        pipeline_config.output_directories.raw_directory
        == project_root / "data" / "jobs" / "job-123" / "raw"
    )
