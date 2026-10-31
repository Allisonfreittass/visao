from fastapi import FastAPI

from apps.api.routes import (
    auth,
    behavior,
    cloud,
    cognition,
    conversations,
    curiosity,
    goals,
    health,
    memory,
    study,
    system,
    voice,
)
from apps.api.settings import get_settings
from infrastructure.observability.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="VISÃO API", version="0.0.1")
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(system.router)
    app.include_router(conversations.router)
    app.include_router(memory.router)
    app.include_router(voice.router)
    app.include_router(curiosity.router)
    app.include_router(goals.router)
    app.include_router(behavior.router)
    app.include_router(cognition.router)
    app.include_router(study.router)
    app.include_router(cloud.router)
    return app


app = create_app()
