from pathlib import Path

from startup_founder_email import cli
from startup_founder_email.cli import build_argument_parser, determine_stage_runner
from startup_founder_email.pipeline import PipelineContext


def test_argument_parser_accepts_collect_stage() -> None:
    argument_parser = build_argument_parser()

    parsed_arguments = argument_parser.parse_args(["collect"])

    assert parsed_arguments.stage_name == "collect"
    assert parsed_arguments.project_root == Path.cwd()


def test_argument_parser_accepts_validate_stage() -> None:
    argument_parser = build_argument_parser()

    parsed_arguments = argument_parser.parse_args(["validate"])

    assert parsed_arguments.stage_name == "validate"


def test_determine_stage_runner_returns_callable() -> None:
    stage_runner = determine_stage_runner("normalize")

    assert callable(stage_runner)


def test_main_returns_nonzero_for_unsupported_stage_behavior(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def unsupported_stage_runner(context: PipelineContext) -> int:
        _ = context
        raise NotImplementedError("unsupported")

    monkeypatch.setattr(
        cli,
        "determine_stage_runner",
        lambda stage_name: unsupported_stage_runner,
    )

    exit_code = cli.main(["--project-root", str(tmp_path), "collect"])

    assert exit_code == 1
