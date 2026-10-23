# Believ: API documentation, 23 October 2026

Channel: Believ's API portal, https://api.believ.com/. The documentation is shown only after
signing in to a free account, so it has no public address. The repository owner registered on
2026-10-23, generated API credentials in the portal's dashboard and copied the documentation
text. The credentials are not recorded here.

The parts this project relies on, in Believ's words:

> 3. Generate API Credentials
>
> In your dashboard: Navigate to the "API Credentials" section. Click the "Generate" button.
> Your client ID and secret will be displayed.
>
> Important: Store your client secret securely. It cannot be retrieved after generation and
> will need to be regenerated if lost.

> Authentication
>
> Once you have your credentials, obtain a bearer token using client credentials:
>
> POST https://api.believ.com/oauth/token with form fields grant_type `client_credentials`,
> client_id and client_secret.

(The documentation gives this step as a PHP example; the address and fields are as shown.)

> Fetching EVSE Data
>
> Use the bearer token to request charger details:
>
> The charger label can be found physically on the charging point - it's typically a 4-6
> character code displayed on the front or side of the unit.
>
> GET https://api.believ.com/1.0/evses/{label}, with the header `Authorization: Bearer <token>`.

> Rate Limiting
>
> Important: Requests are limited to 100 calls per 24hrs, with a maximum of one request per
> second. Exceeding this limit will result in a 429 Too Many Requests response.

The example response for one label holds the EVSE's id, status and capabilities; its location
(id, name, address, city, postal code, country, coordinates, opening times); its connectors
(id, status, standard, max_electric_power, tariff_ids); and the tariffs those connectors name
(currency, and price components with type, price and vat). The documented response codes are
200, 401, 404 ("No charger found with label"), 429 and 503.

The documentation describes no other endpoint, and no way to list locations or chargers. It
states no licence or terms of use for the data.
