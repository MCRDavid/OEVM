"""Load and check the charging plan providers in providers/*.yaml.

    uv run python -m pipeline.plans --validate

Each file is one provider: a roaming app or an operator's own app and subscriptions,
copied by hand from the provider's own pages (schema/provider.py has the rules). The
loader also checks that every operator id a plan names has a file in operators/, so a
plan can only be matched to locations this project knows about.
"""

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from pipeline.registry import ROOT, load_registry
from schema.provider import ProviderFile

PROVIDERS_DIR = ROOT / "providers"


class ProvidersError(ValueError):
    """One or more provider files are invalid."""


def load_providers(
    directory: Path = PROVIDERS_DIR, operator_ids: set[str] | None = None
) -> dict[str, ProviderFile]:
    """Every provider in `directory`, keyed by id. Raises ProvidersError listing every
    problem found."""
    if operator_ids is None:
        operator_ids = set(load_registry())
    problems: list[str] = []
    providers: dict[str, ProviderFile] = {}
    for path in sorted(directory.glob("*.yml")):
        problems.append(f"{path.name}: rename to .yaml so it is picked up")
    for path in sorted(p for p in directory.glob("*.yaml") if not p.name.startswith("_")):
        try:
            provider = ProviderFile.model_validate(yaml.safe_load(path.read_text("utf-8")))
        except ValidationError as exc:
            for err in exc.errors():
                where = ".".join(str(part) for part in err["loc"])
                problems.append(f"{path.name}: {where}: {err['msg']}".replace(": : ", ": "))
            continue
        except yaml.YAMLError as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        if provider.id != path.stem:
            problems.append(f"{path.name}: id {provider.id!r} must match the file name")
        for plan in provider.plans:
            for operator_id in plan.operator_ids:
                if operator_id not in operator_ids:
                    problems.append(
                        f"{path.name}: plan {plan.id!r} names operator {operator_id!r}, "
                        "which has no file in operators/"
                    )
        providers[provider.id] = provider
    if problems:
        raise ProvidersError("\n".join(problems))
    return providers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true", help="check every provider file")
    args = parser.parse_args(argv)
    if not args.validate:
        parser.print_help()
        return 2
    try:
        providers = load_providers()
    except ProvidersError as exc:
        print(exc, file=sys.stderr)
        return 1
    plans = sum(len(p.plans) for p in providers.values())
    print(f"{len(providers)} providers, {plans} plans: all valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
