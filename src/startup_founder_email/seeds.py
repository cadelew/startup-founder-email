"""Read startup seed URLs from CSV files."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StartupSeed:
    """One startup entry from a seeds CSV file."""

    company_name: str | None
    website_url: str


def read_startup_seeds_csv(seeds_csv_path: Path) -> list[StartupSeed]:
    """Read seeds from a CSV with ``company_name,website_url`` (or URL-only) columns."""

    if not seeds_csv_path.is_file():
        raise FileNotFoundError(f"Seeds CSV not found: {seeds_csv_path}")

    seeds: list[StartupSeed] = []
    with seeds_csv_path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames:
            for row in reader:
                seed = parse_startup_seed_row(row)
                if seed is not None:
                    seeds.append(seed)
            return seeds

        csv_file.seek(0)
        plain_reader = csv.reader(csv_file)
        for row in plain_reader:
            if not row or not any(cell.strip() for cell in row):
                continue
            if row[0].strip().lower() in {"company_name", "website_url", "url"}:
                continue
            if len(row) >= 2:
                company_name = row[0].strip() or None
                website_url = row[1].strip()
            else:
                company_name = None
                website_url = row[0].strip()
            if website_url:
                seeds.append(StartupSeed(company_name=company_name, website_url=website_url))
    return seeds


def parse_startup_seed_row(row: dict[str, str]) -> StartupSeed | None:
    """Parse one CSV row into a startup seed."""

    normalized_row = {
        key.strip().lower(): value.strip()
        for key, value in row.items()
        if key and value
    }
    website_url = (
        normalized_row.get("website_url")
        or normalized_row.get("url")
        or normalized_row.get("website")
    )
    if not website_url:
        return None
    company_name = normalized_row.get("company_name") or normalized_row.get("company")
    return StartupSeed(company_name=company_name or None, website_url=website_url)


def startup_seeds_to_target_urls(seeds: list[StartupSeed]) -> tuple[str, ...]:
    """Return deduplicated website URLs from seed rows."""

    seen_urls: set[str] = set()
    target_urls: list[str] = []
    for seed in seeds:
        if seed.website_url not in seen_urls:
            seen_urls.add(seed.website_url)
            target_urls.append(seed.website_url)
    return tuple(target_urls)
