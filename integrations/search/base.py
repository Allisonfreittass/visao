"""Web research providers. Results are untrusted data: never instructions, never executed."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str
    source: str
    retrieved_at: datetime
    updated_at: datetime | None = None


class SearchError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class SearchProvider(Protocol):
    name: str

    def search(self, query: str, max_results: int) -> list[SearchResult]: ...
