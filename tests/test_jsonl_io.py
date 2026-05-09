from dataclasses import dataclass

from startup_founder_email.jsonl_io import iter_jsonl_records, write_jsonl_records


@dataclass(frozen=True)
class ExampleRecord:
    name: str
    score: int


def test_write_jsonl_records_supports_dataclasses_and_dicts(tmp_path) -> None:
    jsonl_path = tmp_path / "records.jsonl"

    write_jsonl_records(
        jsonl_path,
        [
            ExampleRecord(name="Ada", score=10),
            {"name": "Grace", "score": 9},
        ],
    )

    records = list(iter_jsonl_records(jsonl_path))

    assert records == [
        {"name": "Ada", "score": 10},
        {"name": "Grace", "score": 9},
    ]
