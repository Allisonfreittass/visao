"""The screen on the arm's side (docs/TELA.md): off unless braco.json says so, the monitor under
the mouse, and only a real picture goes back."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("visao_braco_tela_u", ROOT / "arm" / "visao_braco.py")
braco = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = braco
spec.loader.exec_module(braco)

MONITORS = """Monitors: 2
 0: +*HDMI-2 1920/480x1080/270+1366+0  HDMI-2
 1: +eDP-1 1366/309x768/173+0+83  eDP-1
"""


def test_the_screen_is_off_unless_braco_json_says_true(tmp_path):
    path = tmp_path / "braco.json"
    data = {"server": "https://s", "token": "t", "projects": {"a": str(tmp_path)}}
    path.write_text(json.dumps(data))
    assert braco.Config.load(path).screen is False
    for value in ("true", 1, "sim"):
        path.write_text(json.dumps({**data, "tela": value}))
        assert braco.Config.load(path).screen is False  # only the JSON true
    path.write_text(json.dumps({**data, "tela": True}))
    assert braco.Config.load(path).screen is True


def test_the_monitor_under_the_mouse_is_the_one_captured(monkeypatch):
    answers = {
        "xdotool": "X=2037\nY=597\nSCREEN=0\nWINDOW=1\n",
        "xrandr": MONITORS,
    }
    monkeypatch.setattr(braco, "_output", lambda argv, seconds=10: answers.get(argv[0], ""))
    assert braco.monitor_under_mouse() == (1920, 1080, 1366, 0)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(braco.shutil, "which", lambda name: f"/usr/bin/{name}")
    [argv] = braco.capture_command(Path("/tmp/x.jpg"))  # noqa: S108
    assert argv[:4] == ["import", "-silent", "-window", "root"]
    assert argv[argv.index("-crop") + 1] == "1920x1080+1366+0"
    assert "1568x1568>" in argv and argv[-1] == "jpg:/tmp/x.jpg"


def test_only_a_jpeg_goes_back(monkeypatch, tmp_path):
    monkeypatch.setattr(braco, "_tell_screen", lambda text: None)

    def fake(target):
        return [[sys.executable, "-c", f"open({str(target)!r}, 'wb').write(b'<html>')"]]

    monkeypatch.setattr(braco, "capture_command", fake)
    assert braco.capture_screen() == {"ok": False, "error": braco.SCREEN_DENIED}
    monkeypatch.setattr(braco, "capture_command", lambda target: None)
    assert braco.capture_screen() == {"ok": False, "error": braco.NO_SCREEN}
