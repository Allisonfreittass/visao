"""Settings turned into the limits the core uses (shared by the routes and the worker)."""

from apps.api.settings import Settings
from core.panels.service import Limits


def panel_limits(settings: Settings) -> Limits:
    return Limits(
        max_active=settings.panels_max_active,
        max_pages=settings.panel_max_pages,
        alert_drop_percent=settings.panel_alert_drop_percent,
    )
