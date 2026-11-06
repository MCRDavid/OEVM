"""Collect the notes (OCPI directions) in saved Monta pages, for the one-off workflow
read-monta-notes-once.yml.

    python3 -I .github/scripts/hidden_notes.py <saved pages folder> <output file>

Reads the pages pipeline.run --save-raw wrote (Monta's adapter has already removed each
record's owner) and writes every location and EVSE directions value that is not empty,
with the location's id, name and city, whether the daily run would keep the location, and
whether the value has the OCPI 2.2.1 shape (a list of DisplayText objects). Prints counts
only, never the notes, as the output is encrypted before it leaves the runner.
"""

import json
import sys
from collections import Counter
from pathlib import Path


def _display_text(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(entry, dict) for entry in value)


def _records(path: Path) -> list:
    body = json.loads(path.read_text(encoding="utf-8"))["response"]["body"]
    if isinstance(body, str):
        body = json.loads(body)
    records = body.get("data") if isinstance(body, dict) else None
    return records if isinstance(records, list) else []


def collect(folder: Path) -> tuple[list[dict], int]:
    notes, read = [], 0
    for path in sorted(folder.glob("locations_page*.json")):
        for record in _records(path):
            if not isinstance(record, dict):
                continue
            read += 1
            evses = [e for e in record.get("evses") or [] if isinstance(e, dict)]
            kept = record.get("publish") is True and any(
                e.get("status") != "REMOVED" for e in evses
            )
            values = [("location", record.get("directions"))]
            values += [(f"evse {e.get('uid')}", e.get("directions")) for e in evses]
            for where, value in values:
                if value in (None, [], ""):
                    continue
                notes.append(
                    {
                        "location_id": record.get("id"),
                        "name": record.get("name"),
                        "city": record.get("city"),
                        "kept_by_daily_run": kept,
                        "where": where,
                        "shape": type(value).__name__,
                        "ocpi_shape": _display_text(value),
                        "value": value,
                    }
                )
    return notes, read


def main() -> None:
    folder, out = Path(sys.argv[1]), Path(sys.argv[2])
    notes, read = collect(folder)
    out.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shapes = Counter((n["where"].split()[0], n["shape"], n["kept_by_daily_run"]) for n in notes)
    print(f"{read} locations read; {len(notes)} notes kept for reading")
    for (where, shape, kept), count in sorted(shapes.items()):
        print(f"  {where} directions as {shape}, kept by the daily run {kept}: {count}")


if __name__ == "__main__":
    main()
