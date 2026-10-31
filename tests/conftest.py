import os

os.environ.setdefault("VISION_ENVIRONMENT", "test")
os.environ.setdefault("VISION_SECRET_KEY", "test-secret-key-with-at-least-32-chars!!")
os.environ.setdefault("VISION_DATABASE_URL", "sqlite://")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from apps.api.main import create_app  # noqa: E402
from infrastructure.database.base import Base  # noqa: E402
from infrastructure.database.session import get_db  # noqa: E402


@pytest.fixture
def engine() -> Iterator[Engine]:
    # A single shared in-memory connection, so the app and the test see the same database.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
