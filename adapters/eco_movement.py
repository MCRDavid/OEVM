"""Adapter for Eco-Movement's PCPR API (registry adapter name: eco_movement_pcpr).

Eco-Movement serves the regulation 10 data of many UK networks from one host,
open-chargepoints.com, as OCPI 2.2.1 (its PCPR API user guide and reference, read
2026-10-07 and 2026-10-26). Each network gives its own token, sent as an
"Authorization: Token <token>" header, so the operator files differ only in the token.

The records are read by the ocpi_221 adapter, with two differences:

- Every request asks for an explicit page size. The documentation gives two different
  defaults (1000 on the getting started page, 1 in the endpoint reference), and the
  largest page it allows is 1000, so pages of 1000 keep the number of requests down.
- Paging stops once the X-Total-Count records have arrived. Every response recorded on
  2026-10-29 still had a next link, to an offset past the last record (for example
  offset=77 when X-Total-Count was 77), so following it would cost one more request per
  module per network.
- date_from is refused. The user guide says it works for locations only, while the
  tariffs reference lists it, so it is left until tested.

The host's rate limits are kept by the operator files' rate_limit, one gap shared by
every operator on the host (adapters.http keeps one timer per host).
"""

from datetime import datetime

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221 import AdapterResult, fetch_feed
from adapters.progress import NO_PROGRESS, PageProgress
from schema.operator import OperatorConfig

# The most records a page may hold ("The minimum value is `1` and the maximum value is
# `1000`", Getting Started, read 2026-10-26).
PAGE_SIZE = 1000


def fetch(
    config: OperatorConfig,
    client: PoliteClient,
    *,
    date_from: datetime | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
    now: datetime | None = None,
    progress: PageProgress = NO_PROGRESS,
) -> AdapterResult:
    if config.adapter != "eco_movement_pcpr":
        raise FeedError(f"{config.id} uses the {config.adapter} adapter, not eco_movement_pcpr")
    if date_from is not None:
        raise FeedError(f"{config.id}: date_from is not tested on Eco-Movement's PCPR API yet")
    return fetch_feed(
        config,
        client,
        page_size=min(page_size or PAGE_SIZE, PAGE_SIZE),
        max_pages=max_pages,
        now=now,
        progress=progress,
        stop_at_total=True,
    )
