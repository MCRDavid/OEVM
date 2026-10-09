"""Progress lines for live runs, so the daily run's log shows how far it has got.

A full run takes about a quarter of an hour, as char.gy's feed is fetched slowly on
purpose, and GitHub shows a step's log while it is being written. Each line is flushed at
once, because Python otherwise holds output back when it is not going to a terminal.

Lines give operator ids, module names and numbers only: never a URL, a key or text from a
feed. Times left are worked out from the pace so far and are labelled as estimates.

    chargy (1 of 3): starting, 6 s between requests
    chargy locations: page 10 of 119 (8%), 500 of 5,949 records, about 12 min 40 s left (estimate)
    chargy locations: done, 119 pages, 5,949 records in 13 min 40 s
"""

import sys
import time
from collections.abc import Callable
from typing import TextIO

from adapters.http import relay_route, required_gap
from schema.operator import OperatorConfig

# A line for the first page of a module, then for every tenth page.
EVERY_PAGES = 10


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}" + ("" if count == 1 else "s")


def duration(seconds: float) -> str:
    """A length of time in words, such as '8 s', '13 min 49 s' or '1 h 5 min'."""
    seconds = max(0, round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s" if seconds else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


def estimate(seconds: float) -> str:
    """A time left, rounded to 10 seconds once it is over a minute, as it is only a guide."""
    return duration(round(seconds / 10) * 10 if seconds >= 60 else seconds)


class RunProgress:
    """Prints how far a live run has got. Adapters report pages through PageProgress."""

    def __init__(
        self,
        *,
        out: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_pages: int | None = None,
        every: int = EVERY_PAGES,
    ):
        self._out = out
        self._clock = clock
        self._max_pages = max_pages
        self._every = every
        self._operator = ""
        self._gap = 0.0
        self._run_started = clock()
        self._operator_started = self._run_started
        # When the current module began: when the operator or the previous module did.
        self._mark = self._run_started
        self._module_started: dict[str, float] = {}
        self._first_page_at: dict[str, float] = {}

    def _say(self, text: str) -> None:
        print(text, file=self._out or sys.stdout, flush=True)

    def _prefix(self, module: str) -> str:
        return f"{self._operator} {module}" if self._operator else module

    def run_started(self, operator_ids: list[str]) -> None:
        self._run_started = self._clock()
        self._say(
            f"Fetching {_plural(len(operator_ids), 'operator')}, one at a time: "
            + ", ".join(operator_ids)
        )

    def operator_started(self, config: OperatorConfig, *, number: int, count: int) -> None:
        """Raises FeedError, as the client would, if the relay is only half set up."""
        self._operator = config.id
        self._operator_started = self._mark = self._clock()
        self._module_started, self._first_page_at = {}, {}
        self._gap = required_gap(config)
        via = ", through the relay" if relay_route(config) else ""
        self._say(
            f"{config.id} ({number} of {count}): starting, {self._gap:g} s between requests{via}"
        )

    def page(
        self,
        module: str,
        *,
        pages: int,
        records: int,
        total_records: int | None = None,
        total_pages: int | None = None,
    ) -> None:
        now = self._clock()
        started = self._module_started.setdefault(module, self._mark)
        if pages == 1:
            self._first_page_at[module] = now
        try:
            line = self._page_line(module, now, started, pages, records, total_records, total_pages)
        except (ArithmeticError, ValueError):
            # A total too large to work with: show the page and the records only. Progress
            # must never stop a fetch.
            due = pages == 1 or pages % self._every == 0
            line = f"{self._prefix(module)}: page {pages:,}, {_plural(records, 'record')}"
            line = line if due else None
        if line:
            self._say(line)

    def _page_line(
        self,
        module: str,
        now: float,
        started: float,
        pages: int,
        records: int,
        total_records: int | None,
        total_pages: int | None,
    ) -> str | None:
        """The line for this page, or None when it is not due."""
        if total_pages is None and total_records is not None and 0 < records <= total_records:
            # The pages still to come at the size of the pages so far, rounded up.
            total_pages = pages + -(-(total_records - records) * pages // records)
        if total_pages is not None and self._max_pages is not None:
            total_pages = min(total_pages, self._max_pages)
        if total_pages is not None and pages >= total_pages:
            return None  # module_done says the rest
        if pages != 1 and pages % self._every:
            return None

        if total_pages is None:
            where = f"page {pages:,}"
        else:
            where = f"page {pages:,} of {total_pages:,} ({pages * 100 // total_pages}%)"
        if total_records is not None:
            counted = f"{records:,} of {total_records:,} records"
        else:
            counted = _plural(records, "record")
        line = f"{self._prefix(module)}: {where}, {counted}"
        if total_pages is not None:
            # The pace between pages so far. The first request to a host has no gap before
            # it, so the pace is never taken as faster than the gap the client keeps.
            if pages > 1:
                pace = (now - self._first_page_at.get(module, started)) / (pages - 1)
            else:
                pace = now - started
            left = max(pace, self._gap) * (total_pages - pages)
            line += f", about {estimate(left)} left (estimate)"
        elif total_records is None:
            line += " (the feed does not say how many there are)"
        return line

    def module_done(self, module: str, *, pages: int, records: int, complete: bool) -> None:
        now = self._clock()
        started = self._module_started.pop(module, self._mark)
        self._first_page_at.pop(module, None)
        self._mark = now
        took = duration(now - started)
        counts = f"{_plural(pages, 'page')}, {_plural(records, 'record')}"
        if complete:
            self._say(f"{self._prefix(module)}: done, {counts} in {took}")
        else:
            self._say(f"{self._prefix(module)}: incomplete, {counts} in {took} (see the report)")

    def operator_done(self, operator_id: str, *, requests: int) -> None:
        took = duration(self._clock() - self._operator_started)
        self._say(f"{operator_id}: finished in {took}, {_plural(requests, 'request')}")

    def operator_failed(self, operator_id: str) -> None:
        took = duration(self._clock() - self._operator_started)
        self._say(f"{operator_id}: failed after {took} (the error follows)")

    def run_done(self, *, fetched: int, failed: list[str]) -> None:
        took = duration(self._clock() - self._run_started)
        line = f"Fetching finished in {took}: {fetched:,} fetched"
        if failed:
            line += f", {len(failed):,} failed ({', '.join(failed)})"
        self._say(line)
