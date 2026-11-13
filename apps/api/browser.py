from functools import lru_cache

from apps.api.settings import get_settings
from integrations.browser.base import Browser
from integrations.browser.playwright_browser import PlaywrightBrowser


@lru_cache
def get_browser() -> Browser | None:
    """Override point for tests. None when no browser is configured (docs/NAVEGADOR.md)."""
    settings = get_settings()
    if not settings.browser_ws_url and not settings.browser_executable_path:
        return None
    return PlaywrightBrowser(
        ws_endpoint=settings.browser_ws_url,
        executable_path=settings.browser_executable_path,
        timeout_seconds=settings.browser_timeout_seconds,
    )
