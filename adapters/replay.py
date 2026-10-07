"""Serve recorded responses instead of calling a live feed.

Used by the tests and by `python -m pipeline.run --fixtures`, so neither ever touches
the network. Each *.json file in a fixture folder that has a "request" key is one
recorded exchange; requests are matched on URL, ignoring query parameter order and any
credential-like parameters.
"""

import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import httpx

from adapters.http import redact_url
from schema.operator import is_credential_param


def _key(url: str) -> tuple:
    parts = urlsplit(url)
    query = sorted(
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not is_credential_param(name)
    )
    return parts.scheme, parts.netloc, parts.path.rstrip("/"), tuple(query)


class ReplayTransport(httpx.BaseTransport):
    def __init__(self, directory: Path):
        self._responses: dict[tuple, dict] = {}
        for path in sorted(directory.glob("*.json")):
            exchange = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(exchange, dict) and "request" in exchange:
                self._responses[_key(exchange["request"]["url"])] = exchange["response"]
        self.requested: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(redact_url(url))
        recorded = self._responses.get(_key(url))
        if recorded is None:
            raise LookupError(f"no recorded response for {redact_url(url)}")
        return httpx.Response(
            recorded["status_code"],
            headers=recorded["headers"],
            content=json.dumps(recorded["body"]).encode("utf-8"),
            request=request,
        )
