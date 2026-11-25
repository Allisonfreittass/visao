"""The local Chromium inside a sandbox, with nothing of value in reach (ADR-0026).

On the server the browser has a container of its own, with no secrets and no database
(docs/NAVEGADOR.md). On the owner's machine there is no container: this puts the same walls
around Chromium with what the system already has, the way the arm runs a task's tests
(arm/visao_braco.py, `sandboxed`):

- Linux: bubblewrap. Only /usr, /etc, Chromium's own folder and its profile folder are mounted;
  the home folder (the .env, the database, ~/.ssh) does not exist inside. New namespaces for
  everything but the network, which it needs to read pages.
- macOS: sandbox-exec. Reading the home folder is denied, except Chromium's folder; writing only
  in the profile folder and the temporary folders.

Playwright launches the browser itself and picks the profile folder (`--user-data-dir`), so the
browser it is told to launch is a small wrapper that runs this file, which reads the arguments
and starts the real Chromium inside the sandbox. The environment comes clean from the caller
(PlaywrightBrowser): no key of the app ever reaches the browser.

Only the standard library, and nothing imported from the project: the wrapper runs it with
`python -I`, outside the app.
"""

import os
import shlex
import shutil
import sys
import tempfile
from pathlib import Path

LINUX_TOOL = "bwrap"
MAC_TOOL = "/usr/bin/sandbox-exec"
# Plain names, enough to run Chromium; nothing from the app's environment.
SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def tool() -> str | None:
    """The sandbox this system has, or None (then the browser does not run: never unwalled)."""
    if sys.platform == "darwin":
        return MAC_TOOL if Path(MAC_TOOL).is_file() else None
    if sys.platform.startswith("linux"):
        return shutil.which(LINUX_TOOL)
    return None


def clean_environment() -> dict[str, str]:
    """What the browser gets instead of the app's environment."""
    env = {"PATH": SAFE_PATH, "HOME": tempfile.gettempdir()}
    for name in ("LANG", "LC_ALL", "TZ"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    return env


def _profile_dirs(args: list[str]) -> list[str]:
    return [os.path.realpath(a.split("=", 1)[1]) for a in args if a.startswith("--user-data-dir=")]


def install_dir(chrome: str) -> str:
    """Chromium's folder, with its libraries: beside the executable, or the folder holding the
    .app bundle on the Mac (the libraries are in Contents/Frameworks)."""
    real = os.path.realpath(chrome)
    if ".app/" in real:
        return os.path.dirname(real.split(".app/", 1)[0])
    return os.path.dirname(real)


def linux_command(bwrap: str, chrome: str, args: list[str]) -> list[str]:
    chrome = os.path.realpath(chrome)
    command = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--share-net",  # it reads pages; the request filter in playwright_browser.py still holds
        "--ro-bind", "/usr", "/usr",
    ]  # fmt: skip
    for top in ("/bin", "/sbin", "/lib", "/lib64", "/lib32"):
        if os.path.islink(top):  # merged /usr: the same links inside
            command += ["--symlink", os.readlink(top), top]
        elif os.path.isdir(top):
            command += ["--ro-bind", top, top]
    command += [
        "--ro-bind", "/etc", "/etc",
        # /etc/resolv.conf points here on systemd systems.
        "--ro-bind-try", "/run/systemd/resolve", "/run/systemd/resolve",
        "--ro-bind-try", "/sys/devices/system/cpu", "/sys/devices/system/cpu",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",  # noqa: S108 (an empty /tmp of its own, inside the sandbox)
        "--ro-bind", install_dir(chrome), install_dir(chrome),
    ]  # fmt: skip
    for folder in _profile_dirs(args):
        command += ["--bind", folder, folder]
    inside = "/tmp"  # noqa: S108 (the sandbox's own empty /tmp, not the machine's)
    return [*command, "--setenv", "HOME", inside, "--chdir", inside, "--", chrome, *args]


def _quoted(path: str) -> str:
    if '"' in path or "\\" in path:
        raise ValueError(f"caminho que o perfil do sandbox não aceita: {path}")
    return f'"{path}"'


def mac_profile(chrome: str, args: list[str], home: str) -> str:
    chrome_dir = install_dir(chrome)
    writable = sorted(
        {
            *_profile_dirs(args),
            os.path.realpath(tempfile.gettempdir()),
            "/private/tmp",
            "/private/var/folders",
        }
    )
    allow_write = " ".join(f"(subpath {_quoted(p)})" for p in writable)
    readable = " ".join(f"(subpath {_quoted(p)})" for p in [chrome_dir, *_profile_dirs(args)])
    # The last rule that matches wins: the home folder is closed, then Chromium's own folder and
    # its profile are opened again.
    return (
        "(version 1)(allow default)"
        f"(deny file-read* (subpath {_quoted(os.path.realpath(home))}))"
        f"(allow file-read* {readable})"
        f'(deny file-write*)(allow file-write* {allow_write} (subpath "/dev"))'
    )


def mac_command(chrome: str, args: list[str], home: str) -> list[str]:
    return [MAC_TOOL, "-p", mac_profile(chrome, args, home), chrome, *args]


def command(chrome: str, args: list[str]) -> list[str]:
    sandbox = tool()
    if sandbox is None:
        raise RuntimeError("sem sandbox neste sistema")
    if sandbox == MAC_TOOL:
        return mac_command(chrome, args, str(Path.home()))
    return linux_command(sandbox, chrome, args)


_wrappers: dict[str, Path] = {}


def wrapper(chrome: str) -> Path | None:
    """The executable Playwright launches in Chromium's place; None without a sandbox."""
    if tool() is None:
        return None
    cached = _wrappers.get(chrome)
    if cached is not None and cached.is_file():
        return cached
    folder = Path(tempfile.mkdtemp(prefix="visao-navegador-"))  # 0700
    script = folder / "chromium"
    script.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(sys.executable)} -I {shlex.quote(str(Path(__file__).resolve()))} "
        f'{shlex.quote(chrome)} "$@"\n'
    )
    script.chmod(0o700)
    _wrappers[chrome] = script
    return script


def main(argv: list[str]) -> None:
    chrome, *args = argv
    real = command(chrome, args)
    os.execv(real[0], real)  # noqa: S606 (the sandbox replaces this process)


if __name__ == "__main__":
    main(sys.argv[1:])
