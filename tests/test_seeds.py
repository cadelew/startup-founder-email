from pathlib import Path

from startup_founder_email.seeds import read_startup_seeds_csv, startup_seeds_to_target_urls


def test_read_startup_seeds_csv_reads_company_and_website_columns(tmp_path: Path) -> None:
    seeds_csv_path = tmp_path / "startup_urls.csv"
    seeds_csv_path.write_text(
        "company_name,website_url\n"
        "Tex Software,https://texsoftware.com\n"
        "Example Inc,https://example.com\n",
        encoding="utf-8",
    )

    seeds = read_startup_seeds_csv(seeds_csv_path)

    assert len(seeds) == 2
    assert seeds[0].company_name == "Tex Software"
    assert seeds[0].website_url == "https://texsoftware.com"
    assert startup_seeds_to_target_urls(seeds) == (
        "https://texsoftware.com",
        "https://example.com",
    )
