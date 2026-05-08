"""Errors raised by the hn-cli library."""

from __future__ import annotations


class HNAPIError(Exception):
    """A non-2xx response from one of the upstream Hacker News APIs.

    Callers can branch on `status_code` (e.g. 429/503) to decide whether to
    retry. The library itself never retries; that is a deliberate choice.
    """

    def __init__(self, status_code: int, url: str, message: str = "") -> None:
        self.status_code = status_code
        self.url = url
        self.message = message
        super().__init__(self._format())

    def _format(self) -> str:
        base = f"HN API returned {self.status_code} for {self.url}"
        return f"{base}: {self.message}" if self.message else base
