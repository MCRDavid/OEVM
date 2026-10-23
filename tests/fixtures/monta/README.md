# Monta fixtures

These files are **made up**, in the shape of Monta's UK open data feed. They are not a
recording. Monta's records name each site's owner, often a private individual, so no real
record is kept in this repository. The shape (every field, its type, and the paging
wrapper) was taken on 23 October 2026 from Monta's feed, counting field names and kinds of
value only, and from Monta's Public API documentation:

- https://docs.public-api.monta.com/reference/get-open-data-locations
- https://docs.public-api.monta.com/reference/authentication

Every name, address, id, tariff id and URL below is invented. Postcodes and coordinates
are ordinary city-centre ones, so the UK check (pipeline/geography.py) has real points to
test. `example.invalid` addresses cannot resolve.

| File | Request |
|---|---|
| `token.json` | `POST /api/v1/auth/token` (the client id and secret are never recorded) |
| `locations_1.json` | `/api/v1/open-data/locations?per_page=100&group_by_location=true` |
| `locations_2.json` | the same, with `after=1009` |

What they cover: an owner field on every record (the adapter removes it), coordinates as
strings, a site whose only charger is `REMOVED`, a site with `publish` false, a second
network's party id under Monta, a DC site with two connectors, connectors that name a
tariff id with no tariffs in the feed, and the cursor paging in `meta.pagination`. The
adapter's handling of HTTP 500 answers is tested with made-up responses in
`tests/test_monta.py`.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Made up for this project's tests, in the shape of the real feed, whose attribution is:

Contains data from Monta published under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

The real feed's data belongs to Monta. It is not covered by this project's Apache-2.0 code
licence. See `DATA_LICENCES.md` at the repository root.
