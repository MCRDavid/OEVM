# Finding the data: footers, FAQs, forms and invitations

Where an operator publishes its data, finding the address is often the hardest part. We have found
data links in a website footer, in FAQ answers and in a blog post. Other operators put a form, a
phone line or an agreement in front of their data, and Tesla's only route we found is an
invitation-only portal on its developer website.

## Where the links were

Here is where some of the networks whose data the map uses with no key put their links when we found
them.

| Network | Where the data link was | Checked |
|---|---|---|
| Arnold Clark Charge | Two links in the footer of its charging page, https://www.arnoldclark.com/charge | 10 October 2026 |
| PoGo Charge and Evolt Network | An answer on each one's FAQ page, https://pogocharge.com/faqs/ and https://evoltnetwork.co.uk/faqs/ | 10 October 2026 |
| ChargePlace Scotland | Its "Network Performance" page, https://chargeplacescotland.org/network-performance-2/ | 10 October 2026 |
| Mer UK | Its "Live Charge Point Data" page, https://uk.mer.eco/live-charge-point-data/ | 10 October 2026 |
| ScottishPower Recharge | A blog post, https://www.scottishpower.co.uk/blog/public-ev-charging. Its main charging page says "Open data provided (location and tariff)" but has no link. | 11 October 2026 |
| ParkRecharge | Its "Public Charging and Open Data" page, https://parkrecharge.com/public-charging | 17 October 2026 |

ParkRecharge moved its data to a new address in October 2026. Our daily fetch could not reach the
old address from 14 October, and by 17 October its host name no longer existed. The new address was
on the same page, so the fix was quick, but we saw no notice of the change on the page.

## Tesla

From the research environment, www.tesla.com refuses automated reads (HTTP 403 on 10 October 2026).
Read in a browser on 11 October 2026, its UK Supercharger, support and legal pages and its sitemap
of 1,905 addresses held no open data, regulations or OCPI page, and the addresses
/en_gb/support/charging/open-data and /public-charge-point-regulations answered HTTP 404 (not
found).

The only route we have found is on Tesla's developer website. Its [roaming
page](https://developer.tesla.com/en_GB/docs/charging/roaming) (read 13 October 2026) says "The
Tesla Roaming Portal is currently available on a pilot and invitation basis only". Joining needs a
Tesla Account with multi-factor authentication, then a connection request giving a "connection
scope, Authentication Token, role, URL and Party ID", which Tesla reviews. The signed-in pages offer
a UK scope. The connection is an OCPI credentials exchange: the form asks for the address of the
requester's own OCPI versions endpoint, which under OCPI 2.2.1 the other side calls. A static map
like this one has no such service, so even with an invitation it could not connect without building
one. We found no terms, licence or rate limits on these pages, signed in or not.

## Forms, phone lines and agreements

- **Request forms.** 17 networks in our register are recorded as offering access on request: their
  own pages offer a form, an email address, a phone line or an account (17 October 2026). Many
  request forms pass the request to Eco-Movement, a company that serves the data for several
  networks: Shell Recharge, ubitricity, IONITY, evyve, Source EV, Blink and ESB Energy, and a
  ChargePoint form that also names Raw Charging, ev-point and Lidl. The forms ask for a name and an
  email address, most ask for an organisation (optional on some), and most ask what the data will be
  used for.
- **A phone line.** Smart Charge's FAQ answers "How can I request Smart Charge's open access data
  end point?" by directing requests to its customer support line (10 October 2026).
- **Agreements.** InstaVolt asks for an email, then sends its Open Data Agreement to sign and return
  before issuing credentials. Source EV lists signing an agreement among its steps.
- **Access for named bodies.** Osprey's and FOR EV's pages describe access to their data for
  government bodies and electricity network operators, and do not say whether anyone else may ask.
  Regulation 10(2)(b) separately requires data on request for the Secretary of State and the network
  operators that supply a charge point operator. We have not yet asked Osprey or FOR EV whether, or
  where, they publish their data for the public.
- **A key on the page.** Jolt prints a shared key on its help page, but that page answers automated
  requests with a browser check (HTTP 403).
- **Self-service.** Believ offers a free account at https://api.believ.com/.

## Terms on the data

Regulation 10(5) asks for the data "without any requirement to agree to terms and conditions
regarding the use of that data". The Department for Transport's guidance adds that "terms and
conditions covering the means of access to the data and API(s) are permissible". Some operators set
terms that speak about the data itself, in the request form or in a policy that says using the API
means agreeing to it:

- Fastned's Fair Use Policy: "Fastned retains all rights, title and interest in both the Data and
  the API." (read 10 October 2026)
- Wenea's Open Data Policy: "All rights, title, and interest in the Data and the API remain with
  Wenea." The same policy also says the data "is made publicly available free of charge and under
  open terms". (read 10 October 2026)
- Gridserve's API Fair Use Policy says intellectual property in the API and API data remains
  Gridserve's, and that the API and API data contain confidential and proprietary information (read
  8 October 2026).

Whether these are terms on access or on use is for the operators and the enforcement authority, not
this project, to settle. We plan to ask Fastned and Wenea, among others, about their terms when we
request access. For Gridserve, the project owner decided on 9 October 2026 not to contact it about
its policy; the transparency page records that decision.

## Pages that refuse automated reads

The data is meant to be machine readable, but many pages that point to it refuse machines.
GeniePoint's open data page and Jolt's help page answered automated requests with a browser check
(GeniePoint on 8 October 2026, Jolt on 7 October 2026). From the research environment, Tesla,
ScottishPower, Asda and Tesco refused automated reads on 10 October 2026, and several other sites
built their pages with scripts that showed no links. Pages like these can only be checked by hand in
a browser, which is not practical every day. char.gy's feed itself refused requests part of the way
through a full fetch three times on 8 and 9 October 2026, after 54 to 58 pages.

## Sites that have moved or gone

- Plug-N-Go's web address was a domain for sale on 10 October 2026.
- The addresses we had for Sprint, Electric Blue and Hubsta did not resolve on 10 and 11 October
  2026.
- Liberty Charge appears to be Believ now; pod-point.com redirects to Pod's site, podenergy.com; EB
  Charging's old site redirects to Blink.
- Go Zero's open data page answered "page not found" on 9, 10 and 11 October 2026.
- ChargePlace Scotland says the owners of the charge points on its network will move them to new
  networks by the end of December 2026.

A rename or move can break the links that data users rely on, and we found no complete public list
of data addresses to update.

## Requests sent

As of 17 October 2026 the project has not yet sent an access request to any operator; the texts are
drafted. Each request and reply will be listed with its date on the [transparency
page](transparency/).
