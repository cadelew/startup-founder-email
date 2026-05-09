"""Filesystem helpers for stage output directories."""

from __future__ import annotations

from pathlib import Path

from startup_founder_email.config import OutputDirectoryConfig


def ensure_output_directories_exist(output_directories: OutputDirectoryConfig) -> None:
    """Create all standard pipeline directories if they do not already exist."""

    directories_to_create: tuple[Path, ...] = (
        output_directories.raw_directory,
        output_directories.normalized_directory,
        output_directories.enriched_directory,
        output_directories.generated_directory,
        output_directories.validated_directory,
        output_directories.exported_directory,
        output_directories.logs_directory,
    )

    for directory_path in directories_to_create:
        directory_path.mkdir(parents=True, exist_ok=True)
