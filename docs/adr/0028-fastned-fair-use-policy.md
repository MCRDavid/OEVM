# 0028: Fastned's Fair Use Policy

Date: 2026-10-24. Status: accepted.

Fastned publishes its UK charge point data through its UK Open Data API, which needs a key.
The key is sent by automated email after a form on Fastned's UK Open Data page,
https://www.fastnedcharging.com/en-gb/uk-open-data, and the page is Fastned's Fair Use
Policy for the API. The policy says "By accessing the API you agree to adhere to this Fair
Use Policy". Among other things it says:

- "Fastned retains all rights, title and interest in both the Data and the API."
- Access is "under a limited, non-exclusive, non-transferable, and revocable license for
  permitted use as outlined in this Policy."
- "Any use, adaption, exploitation, distribution, publishing, transmission or dissemination
  of the Data to any third party must at all times acknowledge the source of the Data as
  Fastned."
- "Where the Data is adapted and exploited, distributed, published, transmitted or
  disseminated to a third party by You, You must acknowledge that Fastned's source Data has
  been adapted."
- "You will not misrepresent the Data at any time."
- "Use of Fastned's trademarks, logos, or branding in conjunction with the API or the Data
  requires prior written approval from Fastned."
- It states no numeric rate limit, but "Fastned may throttle your use of the APIs at any
  time."

Regulation 10(5) of the Public Charge Point Regulations 2023 requires the data to be
available "without any requirement to agree to terms and conditions regarding the use of
that data", and the DfT guidance says the data must be open in line with the Open Government
Licence. Because the policy is written for the data itself, the owner's standing rule of
10 October 2026 on general website or charging terms did not settle it, and on 10 October
the operator was recorded as waiting for the owner's decision.

On 24 October 2026 the repository owner decided to agree to the policy through Fastned's
form, and Fastned granted a key the same day.

## Decisions

- **The data is used in line with the Open Government Licence v3.0**, like every other
  operator's (ADR 0002), and keeps Fastned as its source. The policy itself expects the
  data to be published to others, with Fastned acknowledged as its source.
- **The attribution says the data is adapted.** The map always reshapes a feed (prices,
  statuses and opening times in its own format), so Fastned's attribution statement adds
  "Adapted from Fastned's data." to the usual wording. It is shown wherever the other
  operators' statements are: the map, each location's details, the data licences and
  transparency pages and the published files.
- **No Fastned logo or branding** is used, as for every operator.
- **Rate:** no numeric limit is published, so the usual 2 second gap applies and the feed
  is fetched once a day. If Fastned publishes a limit or throttles requests, the operator
  file records it and the gap follows it.
- **The key** is the GitHub Actions secret `FASTNED_API_KEY`, sent in the `x-api-key`
  header, and passed only to the daily fetch step.
- **Visible.** The operator file, `DATA_LICENCES.md` and the transparency page record the
  policy, the owner's decision and its date.

## Consequences

- Fastned is switched on through the `ocpi_221` adapter with no new code.
- If Fastned changes the policy, the operator file is updated and any change to how the data
  is used goes back to the owner.
