"""A real browser that opens public pages for the owner and returns what they show.

Pages are rendered (sites built with JavaScript work), but only read: no logins, no forms sent,
no downloads, nothing kept between visits. A page that asks to prove you are human is reported,
never worked around.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Visit:
    url: str
    ok: bool
    final_url: str = ""
    title: str = ""
    text: str = ""
    # Links on the page (text, absolute URL), for following a search result.
    links: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    failure: str = ""


class Browser(Protocol):
    name: str

    def visit(self, urls: list[str], on_visit: Callable[[str], None] | None = None) -> list[Visit]:
        """Opens each page in turn; `on_visit(url)` is called as each one starts."""
        ...
