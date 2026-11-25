# The Visão's server frozen for the Mac app (docs/APP_MAC.md, ADR-0027).
#
#   pyinstaller --noconfirm desktop/visao-servidor.spec      (from the repository, after the web build)
#
# Folder mode, never one file: a server started at every login would otherwise unpack itself to a
# temporary folder each time (slow, and macOS checks every unpacked file again). The result is
# dist/visao-servidor/, which the Tauri app carries as a resource.
#
# Left out on purpose in this first version: the voice models (the tts and stt extras, about 2 GB)
# and the Playwright driver (the live-page browser). Both stay in the installed way of running.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent


def tree(folder, suffixes):
    """Every file under `folder` with one of these suffixes, kept at the same path."""
    base = ROOT / folder
    return [
        (str(path), str(path.parent.relative_to(ROOT)))
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix in suffixes and "__pycache__" not in path.parts
    ]


datas = [
    (str(ROOT / "alembic.ini"), "."),
    (str(ROOT / ".env.example"), "."),
    (str(ROOT / "README.md"), "."),
    *tree("migrations", {".py", ".mako"}),
    *tree("apps/web/dist", {".html", ".js", ".css", ".svg", ".png", ".ico", ".webmanifest", ".json", ".woff2", ".txt", ".jpg", ".webp"}),
    # What the agent reads to explain how it is built (core/identity/self_knowledge.py).
    *tree("docs", {".md"}),
    *[item for folder in ("apps/api", "apps/worker", "arm", "core", "integrations", "infrastructure") for item in tree(folder, {".py"})],
    *tree("apps/web/src", {".ts", ".tsx", ".css"}),
    # The Composio SDK names its own version in every request (docs/APPS.md).
    *copy_metadata("composio"),
]

hiddenimports = [
    "apps.api.main",
    *collect_submodules("apps", filter=lambda name: not name.startswith(("apps.ios", "apps.web"))),
    *collect_submodules("core"),
    *collect_submodules("integrations"),
    *collect_submodules("infrastructure.database"),
    *collect_submodules("uvicorn"),
    # Imported only inside integrations/composio/client.py, so named here (docs/APPS.md).
    *collect_submodules("composio", filter=lambda name: ".integration_test" not in name),
    *collect_submodules("composio_client"),
    "alembic.runtime.migration",
    "alembic.ddl.sqlite",
    "alembic.ddl.postgresql",
]

analysis = Analysis(
    [str(ROOT / "desktop" / "visao_servidor.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["playwright", "tkinter", "pytest", "kokoro_onnx", "piper", "faster_whisper", "av", "onnxruntime"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="visao-servidor",
    console=True,
    upx=False,
)
COLLECT(exe, analysis.binaries, analysis.datas, name="visao-servidor", upx=False)
