"""Progress lines for live runs, so the daily run's log shows how far it has got.

A full run takes about a quarter of an hour, as char.gy's feed is fetched slowly on
purpose, and GitHub shows a step's log while it is being written. Each line is flushed at
once, because Python otherwise holds output back when it is not going to a terminal.

Lines give operator ids, module names and numbers only: never a URL, a key or text from a
feed. Times left are worked out from the pace so far and are labelled as estimates.

    chargy (1 of 3): starting, 4 s between requests
    chargy locations: page 10 of 119 (8%), 500 of 5,949 records, about 12 min 40 s left (estimate)
    chargy locations: done, 119 pages, 5,949 records in 13 min 40 s

A page line comes for the first page, every tenth page, and any page after a quiet minute
and a half, so a feed with a long gap between requests shows each page. Every 5 minutes a
summary line says how many operators have finished and where the others have got to.
"""

import sys
import threading
import time
from collections.abc import Callable, Mapping
from typing import TextIO

from adapters.http import SHARED_HOST_SECONDS, relay_route, required_gap
from schema.operator import OperatorConfig

# A line for the first page of a module, then for every tenth page, or sooner when an
# operator has said nothing for HEARTBEAT seconds, so slow feeds do not look stalled.
EVERY_PAGES = 10
HEARTBEAT = 90
# How often the whole run's state is summed up, as lines from operators fetched at the
# same time interleave.
SUMMARY_EVERY = 300


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
    """Prints how far a live run has got, for every operator in it.

    Operators on different hosts may be fetched at the same time (pipeline.run), so each
    operator gets its own OperatorProgress, and lines are printed whole, one at a time.
    """

    def __init__(
        self,
        *,
        out: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_pages: int | None = None,
        every: int = EVERY_PAGES,
        heartbeat: float = HEARTBEAT,
        summary_every: float = SUMMARY_EVERY,
    ):
        self._out = out
        self._clock = clock
        self._max_pages = max_pages
        self._every = every
        self._heartbeat = heartbeat
        self._summary_every = summary_every
        self._count = 0
        self._finished: set[str] = set()
        self._lock = threading.Lock()
        self._run_started = clock()
        self._operators: dict[str, OperatorProgress] = {}
        self._last_summary = self._run_started

    def _say(self, text: str) -> None:
        with self._lock:
            print(text, file=self._out or sys.stdout, flush=True)
            now = self._clock()
            if self._count and now - self._last_summary >= self._summary_every:
                summary = self._summary(now)
                if summary:
                    self._last_summary = now
                    print(summary, file=self._out or sys.stdout, flush=True)

    def _summary(self, now: float) -> str | None:
        running = [
            f"{id_} ({reporter.where})" if reporter.where else id_
            for id_, reporter in self._operators.items()
            if id_ not in self._finished
        ]
        line = (
            f"== Progress after {duration(now - self._run_started)}: "
            f"{len(self._finished):,} of {self._count:,} operators finished"
        )
        return f"{line}; still fetching: {', '.join(running)}" if running else None

    def run_started(self, groups: list[list[str]], turns: Mapping[int, int] | None = None) -> None:
        """groups: operator ids that share a host, fetched one after another, except the
        groups numbered (from 0) in turns, whose operators are fetched together, as the
        owner reads their limits per key, with at most turns[n] requests at once."""
        self._run_started = self._last_summary = self._clock()
        count = self._count = sum(len(group) for group in groups)
        together = "".join(
            f" The {len(groups[n])} operators in the group with {groups[n][0]} are fetched "
            "together, "
            + ("one request at a time" if at_once == 1 else f"up to {at_once} requests at once")
            + ", as their limits are read per key."
            for n, at_once in sorted((turns or {}).items())
        )
        if len(groups) <= 1:
            self._say(
                f"Fetching {_plural(count, 'operator')}, one at a time: "
                + ", ".join(id_ for group in groups for id_ in group)
                + ("." + together if together else "")
            )
            return
        self._say(
            f"Fetching {_plural(count, 'operator')} in {len(groups)} groups at the same "
            "time, one operator at a time within each group, as no two groups share a "
            "host: "
            + "; ".join(", ".join(group) for group in groups)
            + ("." + together if together else "")
        )

    def operator_started(
        self, config: OperatorConfig, *, number: int, count: int
    ) -> "OperatorProgress":
        """Raises FeedError, as the client would, if the relay is only half set up."""
        gap = required_gap(config)
        via = ", through the relay" if relay_route(config) else ""
        pace = f"{gap:g} s between requests"
        if config.limits_per_key is not None and config.limits_as_allowance is not None:
            # Read as an allowance, pages can come SHARED_HOST_SECONDS apart.
            gap, pace = SHARED_HOST_SECONDS, "within its limits read as an allowance"
        reporter = OperatorProgress(self, config.id, gap)
        self._operators[config.id] = reporter
        self._say(f"{config.id} ({number} of {count}): starting, {pace}{via}")
        return reporter

    def operator_done(self, operator_id: str, *, requests: int) -> None:
        self._finished.add(operator_id)
        took = duration(self._clock() - self._operators[operator_id].started)
        self._say(f"{operator_id}: finished in {took}, {_plural(requests, 'request')}")

    def operator_failed(self, operator_id: str) -> None:
        """Also for an operator that failed before it started, such as a half-set relay."""
        self._finished.add(operator_id)
        now = self._clock()
        reporter = self._operators.get(operator_id)
        took = duration(now - (reporter.started if reporter else now))
        self._say(f"{operator_id}: failed after {took} (the error follows)")

    def run_done(self, *, fetched: int, failed: list[str]) -> None:
        took = duration(self._clock() - self._run_started)
        line = f"Fetching finished in {took}: {fetched:,} fetched"
        if failed:
            line += f", {len(failed):,} failed ({', '.join(failed)})"
        self._say(line)


class OperatorProgress:
    """Page and module lines for one operator. Adapters report to it as a PageProgress."""

    def __init__(self, run: RunProgress, operator: str, gap: float):
        self._run = run
        self._operator = operator
        self._gap = gap
        self.started = run._clock()
        # When the current module began: when the operator or the previous module did.
        self._mark = self.started
        self._module_started: dict[str, float] = {}
        self._first_page_at: dict[str, float] = {}
        self._last_line_at = self.started
        # Where the operator has got to, for the run's summary lines.
        self.where = ""

    def _say(self, text: str) -> None:
        self._last_line_at = self._run._clock()
        self._run._say(text)

    def _prefix(self, module: str) -> str:
        return f"{self._operator} {module}"

    def page(
        self,
        module: str,
        *,
        pages: int,
        records: int,
        total_records: int | None = None,
        total_pages: int | None = None,
    ) -> None:
        now = self._run._clock()
        started = self._module_started.setdefault(module, self._mark)
        if pages == 1:
            self._first_page_at[module] = now
        self.where = f"{module} page {pages:,}"
        try:
            line = self._page_line(module, now, started, pages, records, total_records, total_pages)
        except (ArithmeticError, ValueError):
            # A total too large to work with: show the page and the records only. Progress
            # must never stop a fetch.
            due = pages == 1 or pages % self._run._every == 0 or self._quiet(now)
            line = f"{self._prefix(module)}: page {pages:,}, {_plural(records, 'record')}"
            line = line if due else None
        if line:
            self._say(line)

    def _quiet(self, now: float) -> bool:
        return now - self._last_line_at >= self._run._heartbeat

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
        if total_pages is not None and self._run._max_pages is not None:
            total_pages = min(total_pages, self._run._max_pages)
        if total_pages is not None:
            self.where = f"{module} page {pages:,} of {total_pages:,}"
        if total_pages is not None and pages >= total_pages:
            return None  # module_done says the rest
        if pages != 1 and pages % self._run._every and not self._quiet(now):
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
        now = self._run._clock()
        started = self._module_started.pop(module, self._mark)
        self._first_page_at.pop(module, None)
        self._mark = now
        self.where = ""
        took = duration(now - started)
        counts = f"{_plural(pages, 'page')}, {_plural(records, 'record')}"
        if complete:
            self._say(f"{self._prefix(module)}: done, {counts} in {took}")
        else:
            self._say(f"{self._prefix(module)}: incomplete, {counts} in {took} (see the report)")
