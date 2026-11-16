"""What the last database backup left behind (deploy/backup.sh writes it; docs/BACKUP.md).

The backup runs on the host, outside the app; it writes `last.json` (the last run, good or not)
and `last_ok.json` (the last good one) in a folder mounted read-only into the API and the worker.
This only reads them, so a broken or late backup is said in the morning briefing instead of being
found out the day the database is needed.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

STALE = timedelta(hours=36)


def _read(directory: str, name: str) -> dict | None:
    try:
        data = json.loads((Path(directory) / name).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _at(data: dict | None) -> datetime | None:
    try:
        return datetime.fromisoformat(str((data or {}).get("at", "")).replace("Z", "+00:00"))
    except ValueError:
        return None


def problem(directory: str | None, now: datetime | None = None) -> str | None:
    """A sentence for the owner when the backup needs them; None when all is well or when this
    server has no backup set up (development)."""
    if not directory or not Path(directory).is_dir():
        return None
    now = now or datetime.now(UTC)
    last, good = _read(directory, "last.json"), _read(directory, "last_ok.json")
    if last is None and good is None:
        return "o backup do banco ainda não rodou nenhuma vez neste servidor"
    if last is not None and last.get("ok") is not True:
        return f"o backup do banco falhou na etapa {last.get('step', '?')} na última vez que rodou"
    good_at = _at(good)
    if good_at is None or now - good_at > STALE:
        when = f"{good_at:%d/%m}" if good_at else "nenhum"
        return f"o último backup bom do banco é de {when}: o da madrugada não rodou"
    if (good or {}).get("offsite") == "failed":
        return "o backup do banco foi feito no servidor, mas a cópia fora dele falhou"
    return None
