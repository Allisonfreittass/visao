import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.push import configure_push
from apps.api.routes import apps as owner_apps
from apps.api.routes import (
    arm,
    artifacts,
    attachments,
    auth,
    behavior,
    cloud,
    cognition,
    conversations,
    curiosity,
    evolution,
    goals,
    google,
    health,
    memory,
    mind,
    onboarding,
    owner_goals,
    panels,
    projects,
    push,
    share,
    study,
    system,
    voice,
)
from apps.api.settings import get_settings
from apps.api.web import mount_web
from infrastructure.observability.logging import configure_logging
from integrations.idle_cache import VOICE_IDLE

logger = logging.getLogger(__name__)

# How long shutdown waits for the job in hand. Longer than that, the thread is a daemon and goes
# with the process; the job's lease runs out and it goes back to the queue.
WORKER_STOP_SECONDS = 15.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """With VISION_WORKER_IN_API, the worker runs as a thread of this process (one Python on the
    owner's machine instead of two); without it, the API runs alone, as on the server."""
    settings = get_settings()
    stop = threading.Event()
    thread = None
    if settings.worker_in_api:
        from apps.worker.main import serve

        thread = threading.Thread(
            target=serve, args=(stop, settings), name="visao-worker", daemon=True
        )
        thread.start()
    app.state.worker_thread = thread
    try:
        yield
    finally:
        if thread is not None:
            stop.set()
            thread.join(WORKER_STOP_SECONDS)
            if thread.is_alive():
                logger.warning(
                    "worker still busy at shutdown", extra={"event": "worker_stop_timeout"}
                )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_push(settings)
    VOICE_IDLE.set(settings.voice_idle_minutes * 60)
    app = FastAPI(title="VISÃO API", version="0.0.1", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(conversations.router)
    app.include_router(attachments.router)
    app.include_router(artifacts.router)
    app.include_router(projects.router)
    app.include_router(memory.router)
    app.include_router(voice.router)
    app.include_router(curiosity.router)
    app.include_router(goals.router)
    app.include_router(owner_goals.router)
    app.include_router(behavior.router)
    app.include_router(cognition.router)
    app.include_router(mind.router)
    app.include_router(onboarding.router)
    app.include_router(push.router)
    app.include_router(study.router)
    app.include_router(cloud.router)
    app.include_router(evolution.router)
    app.include_router(arm.router)
    app.include_router(google.router)
    app.include_router(owner_apps.router)
    app.include_router(panels.router)
    app.include_router(share.router)
    if settings.web_dir:
        # Last: the site's catch-all must come after every API route.
        mount_web(app, settings.web_dir)
    return app


app = create_app()
