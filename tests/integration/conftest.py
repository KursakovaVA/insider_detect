from __future__ import annotations

import uuid as _uuid
from typing import Any, Callable

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from app.api.deps import get_db
from app.db import Base
from app.main import app as fastapi_app
from app.rules_engine import load_rules

import app.models 
import app.models.alert  
import app.models.event  
import app.models.profile  


def pytest_collection_modifyitems(config, items):
    integration_marker = pytest.mark.integration
    for item in items:
        if "tests/integration/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(integration_marker)


BAIT_FILE_PATH = "/srv/ftp/bait/salary_report_2025.txt"


@pytest.fixture(scope="session")
def postgres_container():
    try:
        container = PostgresContainer(
            image="postgres:17-alpine",
            username="test",
            password="test",
            dbname="insider_test",
            driver="psycopg",
        )
        container.start()
    except Exception as exc:
        pytest.skip(f"Docker недоступен — интеграционные тесты пропущены: {exc}")

    yield container

    container.stop()


@pytest.fixture(scope="session")
def engine(postgres_container):
    url = postgres_container.get_connection_url()

    engine = sa.create_engine(url, future=True, pool_pre_ping=True)
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def _clean_tables(engine, request):
    if "integration" not in str(request.node.fspath):
        yield
        return

    yield

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "TRUNCATE TABLE alerts, events, profiles RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def db_session(session_factory) -> Session:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory) -> TestClient:
    fastapi_app.state.ruleset = load_rules("rules/rules.yaml")

    def _override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(fastapi_app) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def ruleset():
    return load_rules("rules/rules.yaml")


@pytest.fixture
def make_event_payload():
    from datetime import datetime, timezone

    def _make(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "event_id": str(_uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "cowrie",
            "src_ip": "10.0.0.99",
            "action": "login_success",
            "object": None,
            "trap_id": "sensor_a",
            "user": "root",
            "host": "sensor_a",
            "raw": {"test": True},
        }
        base.update(overrides)
        return base

    return _make


@pytest.fixture
def ingest(client: TestClient, make_event_payload) -> Callable[..., dict[str, Any]]:
    def _ingest(**overrides: Any) -> dict[str, Any]:
        payload = make_event_payload(**overrides)
        resp = client.post("/api/v1/ingest", json=payload)
        assert resp.status_code == 200, resp.text
        return payload

    return _ingest


@pytest.fixture
def ingest_bait(ingest) -> Callable[..., dict[str, Any]]:
    def _ingest_bait(**overrides: Any) -> dict[str, Any]:
        defaults = {"action": "file_download", "object": BAIT_FILE_PATH}
        defaults.update(overrides)
        return ingest(**defaults)

    return _ingest_bait
