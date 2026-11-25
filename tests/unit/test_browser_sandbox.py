"""The local Chromium walled in (integrations/browser/sandbox.py, ADR-0026): no keys in its
environment, no home folder in reach, and no browser at all where there is no sandbox."""

import glob
import os
import shutil
import sys
from pathlib import Path

import pytest

from integrations.browser import sandbox
from integrations.browser.playwright_browser import NO_SANDBOX, PlaywrightBrowser

CHROME = "/opt/chromium/chrome-linux64/chrome"
ARGS = ["--headless", "--user-data-dir=/tmp/playwright_chromiumdev_profile-abc", "--no-sandbox"]


def test_the_browser_never_gets_the_app_keys(monkeypatch):
    monkeypatch.setenv("VISION_SECRET_KEY", "segredo")
    monkeypatch.setenv("VISION_LLM_API_KEY", "sk-segredo")
    monkeypatch.setenv("LANG", "pt_BR.UTF-8")
    env = sandbox.clean_environment()
    assert set(env) <= {"PATH", "HOME", "LANG", "LC_ALL", "TZ"}
    assert "segredo" not in repr(env)
    assert env["LANG"] == "pt_BR.UTF-8"


def test_on_linux_only_the_system_chromium_and_its_profile_are_mounted():
    command = sandbox.linux_command("/usr/bin/bwrap", CHROME, ARGS)
    pairs = list(zip(command, command[1:], command[2:], strict=False))
    assert ("--ro-bind", "/usr", "/usr") in pairs
    assert ("--ro-bind", "/opt/chromium/chrome-linux64", "/opt/chromium/chrome-linux64") in pairs
    profile = "/tmp/playwright_chromiumdev_profile-abc"  # noqa: S108
    assert ("--bind", profile, profile) in pairs
    assert "--unshare-all" in command and "--die-with-parent" in command
    home = str(Path.home())
    assert not any(part == home or part.startswith(home + os.sep) for part in command)
    assert command[command.index("--") + 1 :] == [CHROME, *ARGS]


def test_on_the_mac_the_home_is_closed_and_chromium_opened_again():
    chrome = (
        "/Users/dono/Library/Caches/ms-playwright/chromium-1/chrome-mac/"
        "Chromium.app/Contents/MacOS/Chromium"
    )
    profile = sandbox.mac_profile(chrome, ARGS, "/Users/dono")
    closed = profile.index('(deny file-read* (subpath "/Users/dono"))')
    opened = profile.index(
        '(subpath "/Users/dono/Library/Caches/ms-playwright/chromium-1/chrome-mac")'
    )
    assert closed < opened  # the last matching rule wins
    assert "(deny file-write*)" in profile
    assert sandbox.mac_command(chrome, ARGS, "/Users/dono")[:2] == [sandbox.MAC_TOOL, "-p"]


def test_a_path_the_mac_profile_cannot_quote_is_refused():
    with pytest.raises(ValueError):
        sandbox.mac_profile('/Users/dono/"x"/chrome', [], "/Users/dono")


def test_the_wrapper_runs_this_file_isolated(monkeypatch):
    monkeypatch.setattr(sandbox, "tool", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(sandbox, "_wrappers", {})
    script = sandbox.wrapper(CHROME)
    text = script.read_text()
    assert text.startswith("#!/bin/sh\nexec ") and " -I " in text
    assert str(Path(sandbox.__file__).resolve()) in text and '"$@"' in text
    assert script.stat().st_mode & 0o777 == 0o700
    assert sandbox.wrapper(CHROME) == script  # one per Chromium, not one per page


def test_without_a_sandbox_the_local_browser_does_not_open(monkeypatch):
    monkeypatch.setattr(sandbox, "tool", lambda: None)
    browser = PlaywrightBrowser(executable_path=CHROME)
    assert browser.launch_options() is None
    visits = browser.visit(["https://example.com"])
    assert visits[0].ok is False and visits[0].failure == NO_SANDBOX


def test_sandbox_off_on_purpose_still_keeps_the_keys_out(monkeypatch):
    monkeypatch.setenv("VISION_SECRET_KEY", "segredo")
    options = PlaywrightBrowser(executable_path=CHROME, sandboxed=False).launch_options()
    assert options["executable_path"] == CHROME
    assert "VISION_SECRET_KEY" not in options["env"]


def _headless_shell() -> str | None:
    found = glob.glob(
        os.path.expanduser(
            "~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"
        )
    )
    return sorted(found)[-1] if found else None


@pytest.mark.skipif(
    not (sys.platform.startswith("linux") and shutil.which("bwrap") and _headless_shell()),
    reason="needs bubblewrap and Playwright's Chromium",
)
def test_inside_bubblewrap_chromium_reads_a_page_but_not_the_home_folder(tmp_path):
    from playwright.sync_api import Error, sync_playwright

    secret = Path.home() / ".visao-teste-sandbox.txt"
    secret.write_text("VISION_SECRET_KEY=segredo")
    try:
        options = PlaywrightBrowser(executable_path=_headless_shell()).launch_options()
        assert options is not None
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(**options)
            try:
                page = browser.new_page()
                page.goto("data:text/html,<p>ao vivo</p>")
                assert page.inner_text("p") == "ao vivo"
                with pytest.raises(Error, match="ERR_FILE_NOT_FOUND"):
                    page.goto(secret.as_uri())
                # The same file outside the sandbox opens, so the wall is what stopped it.
                outside = runtime.chromium.launch(
                    executable_path=_headless_shell(), env=sandbox.clean_environment()
                )
                try:
                    other = outside.new_page()
                    other.goto(secret.as_uri())
                    assert "segredo" in other.inner_text("body")
                finally:
                    outside.close()
            finally:
                browser.close()
    finally:
        secret.unlink()
