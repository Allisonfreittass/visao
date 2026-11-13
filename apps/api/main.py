from fastapi import FastAPI

from apps.api.push import configure_push
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
    projects,
    push,
    study,
    system,
    voice,
)
from apps.api.settings import get_settings
from infrastructure.observability.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_push(settings)
    app = FastAPI(title="VISÃO API", version="0.0.1")
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
    return app


app = create_app()
