# Monta's UK feed: one list for many small networks, almost no prices

Monta, whose software runs the chargers of many UK site owners, publishes one list of their UK
charge points through its Public API. The map has used it since 23 October 2026. It needs an access
token, one location in it cannot be sent, most of the locations it lists have every charger marked
as removed, and only a handful carry prices. This post sets out what we found and what we tried.

## How the list is reached

Monta's [Public API
documentation](https://docs.public-api.monta.com/reference/get-open-data-locations) describes the
endpoint as "a cursor-paginated list of publicly accessible (or roaming-enabled) charge points in the
United Kingdom in OCPI 2.2.1 Location format", "Intended for AFIR-style aggregators and government
open-data consumers". Reading it needs an access token, requested with the client id and secret of an
application registered in Monta's portal by a signed-in Monta user. The project registered one on 22
October 2026. The pages read on 23 October 2026 set out no licence or terms for the data.

Monta's [Integration Notes](https://docs.public-api.monta.com/reference/integration-notes) give one
limit: "10 requests per minute across all applications of a single user". The limit is per user, not
per application, so a second application or requests sent side by side would add nothing. The map
reads the list once a day, 7 seconds apart, in pages of 100. On 23 October 2026 a full read took 81
requests and just under 13 minutes. None of the responses checked on 23 October 2026 carried rate
limit headers.

## What the list holds

Read in full on 23 October 2026:

| | Locations |
|---|---|
| Listed | 4,775 |
| Not kept: every charger marked REMOVED | 4,036 |
| Not kept: publish flag false, of the rest | 10 |
| Kept and on the map, all in the UK | 729 |

Most locations carry Monta's own party id, MON. Others carry the party ids and names of networks that
run on Monta, among them evyve charging network (EVY, 225 locations) and Urban Fox (UFX, 152). The
EVSE ids we tried at UK sites begin DK*MON, with Denmark's country code.

OCPI 2.2.1 says "A Location without any valid EVSE object can be considered expired and should no
longer be displayed", so locations whose chargers are all marked REMOVED are left off the map.

One location, after the 1,675th in the list, makes Monta's server answer HTTP 500 ("An unexpected
error occurred") every time, whether it is asked for in a page of 100, of 10 or on its own (22 and 23
October 2026). The map skips past it, so the [feed health page](status/) shows Monta's runs as
incomplete. Each location also names its site owner; the map does not keep that field.

## Prices

In the 4,775 locations read on 23 October 2026, 17,391 of the 17,675 connectors name a tariff id,
but only 5 locations carry any tariff. Monta puts tariffs inside each charger's record (a Monta
addition to OCPI), a list its documentation says is "empty when no OCPI tariff is available for the
charge point". Their prices are given excluding VAT, with a separate VAT field. In a run on 23 October 2026 that
gave 2 tariffs, which priced 54 of the 2,785 connectors on the map. Every other Monta connector shows
"Price unknown". Monta's [help
pages](https://monta.com/help/en_US/monta-hub-charge-points-pricing-access) describe operators
setting their own prices in Monta Hub, its back office.

We looked for any other price in Monta's Public API (read 23 October 2026):

- Its index lists no tariffs, price or quote endpoint beyond the ones below.
- Three AFIR endpoints carry "ad-hoc" prices. The list of charge points and the bulk status endpoint
  take a country, and on 23 October 2026 both answered HTTP 400 for GB: "Unsupported country 'GB'.
  Allowed values: DK, BE".
- The single-charger endpoint, GET /api/v1/afir/charge-points/{evseId}/status, "Returns the current
  availability status and ad-hoc price for a single EVSE". Asked on 23 October 2026 for four UK
  chargers taken from the open data list, it answered HTTP 404 (not found) by each charger's EVSE id,
  and HTTP 400 ("Bad request to upstream service") with the separators removed.
- As a check, the same endpoint was asked for two of Monta's Danish chargers, taken from its AFIR
  status list for Denmark. Both answered HTTP 200 with a price in Danish kroner. So the endpoint
  works, but the UK chargers in the open data list are not in it.

So, as of 23 October 2026, the only prices for Monta's UK chargers that we can read are the few in
the open data list itself. The map does not copy prices from Monta's app or from other aggregators,
which are not the operators' published open data.

## What would help

Our view: if Monta filled in the tariffs its connectors already name, or let its AFIR price
endpoints answer for UK chargers, around 2,700 more connectors could show a price. Either would fit
within the published limit. The bulk status endpoint returns 100 chargers a request, so even a
refresh several times a day would take a few dozen requests. The project owner decided on 23
October 2026 not to ask Monta, so the map will show Monta's prices only where its list gives them.
