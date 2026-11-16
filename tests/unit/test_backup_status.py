"""The morning briefing learns from the backup's status files when it needs the owner
(core/backup_status.py, docs/BACKUP.md)."""

import json
from datetime import UTC, datetime, timedelta

from core import backup_status

NOW = datetime(2026, 11, 18, 11, 0, tzinfo=UTC)


def _write(folder, name, **data):
    (folder / name).write_text(json.dumps(data))


def test_no_backup_set_up_says_nothing(tmp_path):
    assert backup_status.problem(None, NOW) is None
    assert backup_status.problem(str(tmp_path / "nada"), NOW) is None


def test_a_good_backup_from_tonight_says_nothing(tmp_path):
    tonight = (NOW - timedelta(hours=5)).isoformat()
    _write(tmp_path, "last.json", ok=True, at=tonight, step="done", offsite="none")
    _write(tmp_path, "last_ok.json", ok=True, at=tonight, step="done", offsite="none")
    assert backup_status.problem(str(tmp_path), NOW) is None


def test_failed_late_never_run_or_not_copied_out_is_said(tmp_path):
    assert "ainda não rodou" in backup_status.problem(str(tmp_path), NOW)
    old = (NOW - timedelta(days=3)).isoformat()
    _write(tmp_path, "last_ok.json", ok=True, at=old, step="done")
    assert "é de 15/11" in backup_status.problem(str(tmp_path), NOW)
    _write(tmp_path, "last.json", ok=False, at=NOW.isoformat(), step="dump")
    assert "falhou na etapa dump" in backup_status.problem(str(tmp_path), NOW)
    fresh = (NOW - timedelta(hours=5)).isoformat()
    _write(tmp_path, "last.json", ok=True, at=fresh, step="done", offsite="failed")
    _write(tmp_path, "last_ok.json", ok=True, at=fresh, step="done", offsite="failed")
    assert "cópia fora dele falhou" in backup_status.problem(str(tmp_path), NOW)
