"""The Visão's server inside the Mac app: the `visao` command, frozen by PyInstaller
(visao-servidor.spec, docs/APP_MAC.md). The app runs `visao-servidor iniciar --porta N`."""

from apps.visao_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
