from pathlib import Path

from startup_founder_email.config import build_output_directory_config
from startup_founder_email.paths import ensure_output_directories_exist


def test_ensure_output_directories_exist_creates_pipeline_folders(tmp_path: Path) -> None:
    output_directory_config = build_output_directory_config(tmp_path)

    ensure_output_directories_exist(output_directory_config)

    assert output_directory_config.raw_directory.exists()
    assert output_directory_config.validated_directory.exists()
    assert output_directory_config.exported_directory.exists()
