import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFY_DATA_DIR", str(tmp_path))
    backend_path = Path(__file__).resolve().parents[1]
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
    import app.config
    import app.db
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.db)
    import app.models

    importlib.reload(app.models)
    import app.bootstrap
    import app.services.fts
    import app.routers.work
    import app.routers.system
    import app.main

    importlib.reload(app.bootstrap)
    importlib.reload(app.services.fts)
    importlib.reload(app.routers.system)
    importlib.reload(app.routers.work)
    importlib.reload(app.main)
    with TestClient(app.main.app) as test_client:
        yield test_client
