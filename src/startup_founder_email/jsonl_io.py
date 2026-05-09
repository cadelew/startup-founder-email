"""Small JSON Lines helpers shared by pipeline stages."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def iter_jsonl_records(jsonl_path: Path) -> Iterator[dict[str, Any]]:
    """Yield one parsed JSON object for each non-empty line."""

    with jsonl_path.open(encoding="utf-8") as jsonl_file:
        for raw_line in jsonl_file:
            line = raw_line.strip()
            if line:
                yield json.loads(line)


def write_jsonl_records(jsonl_path: Path, records: Iterable[object]) -> None:
    """Write dataclass or dictionary records as newline-delimited JSON."""

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        for record in records:
            json.dump(_as_json_object(record), jsonl_file, sort_keys=True)
            jsonl_file.write("\n")


def _as_json_object(record: object) -> dict[str, Any]:
    """Return a JSON-ready dictionary for one record."""

    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, dict):
        return record
    raise TypeError(f"Unsupported JSONL record type: {type(record).__name__}")
