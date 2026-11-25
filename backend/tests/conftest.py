import os
import sys
import tempfile
from pathlib import Path

# Always isolate tests from both the developer database and the configured model.
test_dir = tempfile.TemporaryDirectory(prefix="zhiheng-test-")
os.environ.update(
    DATA_DIR=test_dir.name,
    DATABASE_URL="sqlite:///" + (Path(test_dir.name) / "test.db").as_posix(),
    DEMO_MODE="1",
    TASK_MODE="local",
    MODEL_BASE_URL="",
    MODEL_NAME="",
    REDIS_URL="",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def server():
    with TestClient(app):
        yield
    from app.db import engine

    engine.dispose()


@pytest.fixture
def login():
    clients = []

    def start(name):
        c = TestClient(app)
        clients.append(c)
        assert (
            c.post("/api/login", json={"username": name, "password": "Physics2027!"}).status_code == 200
        )
        return c

    yield start
    for c in clients:
        c.close()
