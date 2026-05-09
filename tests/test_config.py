from pathlib import Path

from startup_founder_email.config import load_pipeline_config


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
