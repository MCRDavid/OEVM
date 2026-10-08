"""Load and validate the operator registry (operators/*.yaml).

    uv run python -m pipeline.registry --validate

Checks every operator file against schema.operator.OperatorConfig, checks that
each id matches its file name and that any evidence files exist, then prints a
summary. Exits with status 1 if anything is wrong.

Files whose names start with "_" (such as _template.yaml) are not operators.
"""

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from schema.operator import OperatorConfig

ROOT = Path(__file__).resolve().parent.parent
OPERATORS_DIR = ROOT / "operators"


class RegistryError(Exception):
    """One or more registry files are invalid. `problems` lists each one."""

    def __init__(self, problems: list[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


def load_operator_file(path: Path) -> OperatorConfig:
    """Parse and validate one operator file. Raises ValueError or yaml.YAMLError."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("the file must contain a YAML mapping of field names to values")
    return OperatorConfig.model_validate(data)


def _describe(error: dict) -> str:
    # Drop Pydantic's internal labels for union branches, such as "literal['unknown']".
    parts = [
        str(part)
        for part in error["loc"]
        if not (isinstance(part, str) and ("[" in part or part.startswith("constrained-")))
    ]
    location = ".".join(parts)
    return f"{location}: {error['msg']}" if location else error["msg"]


def load_registry(directory: Path = OPERATORS_DIR) -> dict[str, OperatorConfig]:
    """Load every operator in `directory`, keyed by id.

    Evidence file paths are checked relative to the directory's parent (the
    repository root). Raises RegistryError listing every problem found.
    """
    problems: list[str] = []
    operators: dict[str, OperatorConfig] = {}

    for path in sorted(directory.glob("*.yml")):
        problems.append(f"{path.name}: rename to .yaml so the registry picks it up")

    files = sorted(p for p in directory.glob("*.yaml") if not p.name.startswith("_"))
    if not files:
        problems.append(f"no operator files found in {directory}")

    for path in files:
        try:
            config = load_operator_file(path)
        except ValidationError as exc:
            problems.extend(f"{path.name}: {_describe(err)}" for err in exc.errors())
            continue
        except (yaml.YAMLError, ValueError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue

        if config.id != path.stem:
            problems.append(f"{path.name}: id {config.id!r} must match the file name")
        for evidence in config.engagement.evidence:
            if evidence.file is None:
                continue
            if not evidence.file.startswith(f"evidence/{config.id}/"):
                problems.append(f"{path.name}: evidence file must be under evidence/{config.id}/")
            elif not (directory.parent / evidence.file).is_file():
                problems.append(f"{path.name}: evidence file {evidence.file} does not exist")
        operators[config.id] = config

    if problems:
        raise RegistryError(problems)
    return operators


def warnings_for(config: OperatorConfig) -> list[str]:
    """Things that are allowed but should be fixed when possible."""
    warnings = []
    for evidence in config.engagement.evidence:
        if evidence.date == "unknown":
            where = evidence.url or evidence.file
            warnings.append(f"{config.id}: evidence {where} has no date; add the date checked")
    return warnings


def summary(operators: dict[str, OperatorConfig]) -> str:
    enabled = sum(1 for c in operators.values() if c.enabled)
    lines = [
        f"Operator registry is valid: {len(operators)} operators, {enabled} enabled.",
        "",
        f"{'id':<30} {'adapter':<18} {'engagement':<26} {'enabled':<8} secret_name",
    ]
    for config in operators.values():
        lines.append(
            f"{config.id:<30} {config.adapter:<18} {config.engagement.status:<26} "
            f"{'yes' if config.enabled else 'no':<8} {config.auth.secret_name or '-'}"
        )

    needs_secret = [
        f"{c.id} ({c.auth.secret_name})"
        for c in operators.values()
        if c.enabled and c.auth.secret_name
    ]
    if needs_secret:
        lines += [
            "",
            "Enabled operators that need a GitHub Actions secret: " + ", ".join(needs_secret),
        ]
    relayed = [
        f"{c.id} (secrets {c.relay.url_variable} and {c.relay.secret_name})"
        for c in operators.values()
        if c.enabled and c.relay
    ]
    if relayed:
        lines += ["Enabled operators fetched through the relay: " + ", ".join(relayed)]

    warnings = [w for c in operators.values() for w in warnings_for(c)]
    if warnings:
        lines += ["", f"Warnings ({len(warnings)}):"] + [f"  - {w}" for w in warnings]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.registry", description="Operator registry tools."
    )
    parser.add_argument(
        "--validate", action="store_true", help="validate every operator file and print a summary"
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=OPERATORS_DIR,
        help="registry directory (default: operators/)",
    )
    args = parser.parse_args(argv)
    if not args.validate:
        parser.print_help()
        return 2

    try:
        operators = load_registry(args.dir)
    except RegistryError as exc:
        print(f"Operator registry is NOT valid ({len(exc.problems)} problems):", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(summary(operators))
    return 0


if __name__ == "__main__":
    sys.exit(main())
