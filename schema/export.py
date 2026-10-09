"""Export JSON Schema files from the Pydantic models.

Run this after changing any model, and commit the files it writes:

    uv run python -m schema.export

CI runs it with --check, which fails if a committed file is out of date.
"""

import argparse
import json
import sys
from pathlib import Path

from schema.live import LiveSnapshot
from schema.models import Location, Tariff
from schema.operator import OperatorConfig
from schema.provider import ProviderFile
from schema.published import LocationDetail, Manifest, MapLayer, PlansFile, StatusFile

ROOT = Path(__file__).resolve().parent.parent
DIALECT = "https://json-schema.org/draft/2020-12/schema"


def build_schemas() -> dict[Path, dict]:
    """Map each output path to its schema.

    Location and Tariff describe published output, so they use Pydantic's "serialization" mode.
    The operator schema describes the YAML people write, so it uses "validation" mode.
    """
    return {
        ROOT / "schema" / "json" / "location.schema.json": Location.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "tariff.schema.json": Tariff.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "map-layer.schema.json": MapLayer.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "location-detail.schema.json": LocationDetail.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "manifest.schema.json": Manifest.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "status.schema.json": StatusFile.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "live-snapshot.schema.json": LiveSnapshot.model_json_schema(
            mode="serialization"
        ),
        ROOT / "schema" / "json" / "plans.schema.json": PlansFile.model_json_schema(
            mode="serialization"
        ),
        ROOT / "operators" / "schema.json": OperatorConfig.model_json_schema(mode="validation"),
        ROOT / "providers" / "schema.json": ProviderFile.model_json_schema(mode="validation"),
    }


def render(schema: dict) -> str:
    return json.dumps({"$schema": DIALECT, **schema}, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m schema.export", description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write anything; exit with an error if any file is out of date",
    )
    args = parser.parse_args(argv)

    stale = []
    for path, schema in build_schemas().items():
        text = render(schema)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        relative = path.relative_to(ROOT)
        if args.check:
            stale.append(relative)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"Wrote {relative}")

    if stale:
        names = ", ".join(str(p) for p in stale)
        print(
            f"Out of date: {names}. Run 'uv run python -m schema.export' and commit the result.",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print("JSON Schema files are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
