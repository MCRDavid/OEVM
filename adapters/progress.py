"""How an adapter reports each page it fetches, so a long run can show how far it has got.

Adapters call page() after each response and module_done() when a module ends. They pass
the module name and numbers only, never a URL or text from a feed. pipeline.progress
prints them for live runs; NO_PROGRESS ignores them, for replays and tests.
"""

from typing import Protocol


class PageProgress(Protocol):
    def page(
        self,
        module: str,
        *,
        pages: int,
        records: int,
        total_records: int | None = None,
        total_pages: int | None = None,
    ) -> None: ...

    def module_done(self, module: str, *, pages: int, records: int, complete: bool) -> None: ...


class _NoProgress:
    def page(
        self,
        module: str,
        *,
        pages: int,
        records: int,
        total_records: int | None = None,
        total_pages: int | None = None,
    ) -> None:
        return None

    def module_done(self, module: str, *, pages: int, records: int, complete: bool) -> None:
        return None


NO_PROGRESS: PageProgress = _NoProgress()
