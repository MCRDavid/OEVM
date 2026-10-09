# 0006: Publishing the map files

Date: 2026-10-08. Status: accepted.

Blueprint task 7: merge the operators' data and publish a slim GeoJSON layer, one detail
file per location and a manifest. Accept: outputs validate; size logged.

## Decisions

- `uv run python -m pipeline.run --fixtures --publish DIR` (or `--live`) writes
  `DIR/data/locations.geojson`, `DIR/data/loc/<shard>/<key>.json` and
  `DIR/data/manifest.json`. It refuses to write into the committed `site/` folder; the
  deploy step (blueprint task 10) will copy `site/` and add this output.
- **Slim layer:** position, operator, name, highest power, connector standards, EVSE
  count, a price summary ("free" only when a connector is free_confirmed) and `ppk`, the
  cheapest connector's highest price per kWh including VAT, given only when VAT is
  stated. It holds no live status: a daily snapshot would look current when it is not.
  Statuses are in the detail files with their dates. Amended by ADR 0008: `ppk` was
  replaced by `pt`, a price summary worded by `pipeline/pricing.py`, and `cons`, each
  kind of connector with its own price state and price per kWh, so filters can test one
  connector at a time. A location is "free" only when every connector is
  free_confirmed.
- **Detail files** are named by the first 16 hexadecimal characters of the SHA-256 of the
  location id, because ids can contain spaces, and sharded by the first two characters.
  A clash stops the run. Old detail files are removed on each publish.
- **Validation:** every file is checked by reading back the exact bytes about to be
  written against the models in `schema/published.py`. Their JSON Schema is exported to
  `schema/json/` and the tests validate the written files against it.
- **Only switched-on operators** are published, and each operator's attribution and
  licence go into the layer, every detail file and the manifest.
- **Coordinates outside the UK** (latitude 49.8 to 60.95, longitude -8.7 to 1.8) are left
  off the map and listed in the manifest, never corrected. The first real case was
  GeniePoint's Crewe Civic site, whose longitude has the wrong sign. (Since 9 October 2026
  "in the UK" uses the UK's outline as well as these limits, ADR 0016, and obvious swaps
  may be corrected by the owner's decision, ADR 0013.)
- **Size:** measured on 2026-10-08 with the full GeniePoint and Jolt data, the layer is
  about 322 bytes per location, 56 bytes gzipped. 50,000 locations would be about 16 MB,
  2.8 MB gzipped, under the blueprint's 5 MB point for switching to PMTiles. This is an
  estimate from 377 locations; the manifest records real sizes on every publish.
