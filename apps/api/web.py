"""The web app served by the API itself, on one address (docs/research/execucao_local.md, etapa 3).

On the server, Caddy serves the build and sends `/api/*` to the API with the prefix taken off. On
the owner's machine there is no Caddy: with `VISION_WEB_DIR` pointing at the Vite build
(`apps/web/dist`), the API does both:

- `/api/...` reaches the same routes as on the server, the prefix taken off before routing;
- a file of the build is served as is (hashed assets for a year, the rest always revalidated);
- any other page a browser asks for gets `index.html`, so a reload on a screen of the app works;
- anything else is the API's own 404, never an HTML page in place of JSON.

The routes without `/api` keep working, as the Mac's arm and the tests use them.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

PREFIX = "/api"
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "no-cache"


class StripApiPrefix:
    """Takes `/api` off the path, as Caddy and the Vite proxy do, before the routes see it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            path: str = scope.get("path", "")
            if path == PREFIX or path.startswith(PREFIX + "/"):
                scope = dict(scope)
                scope["path"] = path[len(PREFIX) :] or "/"
                raw = scope.get("raw_path")
                if isinstance(raw, bytes) and raw.startswith(PREFIX.encode()):
                    scope["raw_path"] = raw[len(PREFIX) :] or b"/"
        await self.app(scope, receive, send)


def _inside(root: Path, wanted: Path) -> bool:
    try:
        wanted.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def mount_web(app: FastAPI, web_dir: str | Path) -> None:
    """Serves the build at `web_dir` from this app. Call after every API route is registered."""
    root = Path(web_dir)
    index = root / "index.html"
    if not index.is_file():
        raise FileNotFoundError(
            f"{index} não existe: gere o build com `npm --prefix apps/web run build`"
        )

    app.add_middleware(StripApiPrefix)

    @app.get("/{path:path}", include_in_schema=False)
    async def web(path: str, request: Request) -> Response:
        wanted = root / path
        if path and wanted.is_file() and _inside(root, wanted):
            cache = IMMUTABLE if path.startswith("assets/") else REVALIDATE
            return FileResponse(wanted, headers={"Cache-Control": cache})
        # A screen of the app (no extension, a browser asking for a page): the app takes it.
        if "." not in Path(path).name and "text/html" in request.headers.get("accept", ""):
            return FileResponse(index, headers={"Cache-Control": REVALIDATE})
        return Response('{"detail":"Not Found"}', status_code=404, media_type="application/json")
