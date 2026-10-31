from apps.worker.health import MAX_AGE_SECONDS, beat, is_alive


def test_missing_heartbeat_is_unhealthy(tmp_path):
    assert not is_alive(tmp_path / "hb")


def test_recent_heartbeat_is_healthy_and_stale_is_not(tmp_path):
    path = tmp_path / "hb"
    beat(path)
    mtime = path.stat().st_mtime
    assert is_alive(path, now=mtime + 1)
    assert not is_alive(path, now=mtime + MAX_AGE_SECONDS + 1)
