"""Assemble the website in a build folder (blueprint task 9).

    npm ci                                                  # installs MapLibre
    uv run python -m pipeline.run --fixtures --publish build
    uv run python -m pipeline.build_site --out build

copies the committed site/ pages into the build folder, adds MapLibre GL JS from
node_modules (served from the site itself, so visitors contact no script host), its
licence and the notices of the packages it bundles, and writes assets/config.json.

--offline-style points the map at a plain local style instead of the OpenFreeMap
basemap. Tests and CI use it, because the basemap's terms forbid automated collection
and tests must not depend on outside services.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT

SITE = ROOT / "site"
NODE_MODULES = ROOT / "node_modules"
# The exact version package.json pins; node_modules must hold the same one.
_PACKAGE_JSON = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
MAPLIBRE_VERSION = _PACKAGE_JSON["dependencies"]["maplibre-gl"]
MAPLIBRE_FILES = (
    "maplibre-gl.mjs",
    "maplibre-gl-shared.mjs",
    "maplibre-gl-worker.mjs",
    "maplibre-gl.css",
)
STYLE_URL = "https://tiles.openfreemap.org/styles/liberty"
# Dark mode: OpenFreeMap's dark style, from the same host, fonts and sprites as Liberty.
DARK_STYLE_URL = "https://tiles.openfreemap.org/styles/dark"
# Latitude and longitude limits the map can be panned within: the UK with a margin.
MAX_BOUNDS = [[-11.5, 48.5], [4.5, 61.5]]
OFFLINE_STYLE = {
    "version": 8,
    "name": "Offline style for tests",
    "sources": {},
    "layers": [
        {"id": "background", "type": "background", "paint": {"background-color": "#e4ebef"}}
    ],
}
OFFLINE_DARK_STYLE = {
    "version": 8,
    "name": "Offline dark style for tests",
    "sources": {},
    "layers": [
        {"id": "background", "type": "background", "paint": {"background-color": "#1f2428"}}
    ],
}
LICENCE_NAMES = ("LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE", "LICENCE.txt", "COPYING")


class BuildError(Exception):
    """The site cannot be built as asked."""


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _package(name: str) -> dict:
    path = NODE_MODULES / name / "package.json"
    if not path.exists():
        raise BuildError(f"{name} is not installed; run 'npm ci' first")
    return json.loads(path.read_text(encoding="utf-8"))


def third_party_notices() -> str:
    """The licence of every package MapLibre bundles, as npm installed them."""
    maplibre = _package("maplibre-gl")
    parts = [
        "Third-party notices for MapLibre GL JS "
        f"{maplibre['version']} and the packages bundled into it.\n\n"
        "Each licence text below comes from the version npm installed alongside MapLibre. "
        "The bundled code may come from a slightly earlier version of the same package.\n"
    ]
    for name in sorted(maplibre.get("dependencies", {})):
        package = _package(name)
        licence = package.get("license", "licence not stated")
        heading = f"{name} {package.get('version')} ({licence})"
        texts = [
            (NODE_MODULES / name / file).read_text(encoding="utf-8", errors="replace").strip()
            for file in LICENCE_NAMES
            if (NODE_MODULES / name / file).is_file()
        ]
        if not texts:
            author = package.get("author")
            author = author.get("name") if isinstance(author, dict) else author
            texts = [
                f"No licence file is shipped with this package. Its package.json declares "
                f"the {package.get('license', 'unknown')} licence"
                + (f", author {author}." if author else ".")
            ]
        parts.append(f"{'=' * 72}\n{heading}\n{'=' * 72}\n\n" + "\n\n".join(texts) + "\n")
    return "\n".join(parts)


def build(out: Path, *, offline_style: bool = False) -> list[str]:
    """Copy the site, MapLibre and config into out. Returns what was written."""
    target, site = out.resolve(), SITE.resolve()
    if target == site or target.is_relative_to(site) or site.is_relative_to(target):
        raise BuildError(
            "build into a separate folder, not the committed site/ folder or one inside or "
            "around it"
        )
    version = _package("maplibre-gl")["version"]
    if version != MAPLIBRE_VERSION:
        raise BuildError(
            f"node_modules has maplibre-gl {version}, but {MAPLIBRE_VERSION} is expected; "
            "run 'npm ci'"
        )
    shutil.copytree(SITE, out, dirs_exist_ok=True)

    vendor = out / "vendor" / "maplibre-gl"
    vendor.mkdir(parents=True, exist_ok=True)
    for name in MAPLIBRE_FILES:
        shutil.copy2(NODE_MODULES / "maplibre-gl" / "dist" / name, vendor / name)
    shutil.copy2(NODE_MODULES / "maplibre-gl" / "LICENSE.txt", vendor / "LICENSE.txt")
    (vendor / "THIRD_PARTY_NOTICES.txt").write_text(third_party_notices(), encoding="utf-8")

    # origins: the only hosts besides this site the map may request (main.js enforces it).
    config = {
        "style": STYLE_URL,
        "darkStyle": DARK_STYLE_URL,
        "origins": [_origin(STYLE_URL)],
        "repository": REPOSITORY_URL,
        "maxBounds": MAX_BOUNDS,
        "maplibre": MAPLIBRE_VERSION,
    }
    if offline_style:
        (out / "assets" / "offline-style.json").write_text(
            json.dumps(OFFLINE_STYLE, indent=2) + "\n", encoding="utf-8"
        )
        (out / "assets" / "offline-style-dark.json").write_text(
            json.dumps(OFFLINE_DARK_STYLE, indent=2) + "\n", encoding="utf-8"
        )
        config["style"] = "assets/offline-style.json"
        config["darkStyle"] = "assets/offline-style-dark.json"
        config["origins"] = []
    (out / "assets" / "config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    return [
        f"copied site/ to {out}",
        f"added MapLibre GL JS {version} to {vendor.relative_to(out)}",
        f"map style: {config['style']}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.build_site", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="build folder (not site/)")
    parser.add_argument(
        "--offline-style",
        action="store_true",
        help="use a plain local map style instead of the OpenFreeMap basemap (tests, CI)",
    )
    args = parser.parse_args(argv)
    try:
        lines = build(args.out, offline_style=args.offline_style)
    except BuildError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
