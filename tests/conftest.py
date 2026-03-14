import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly enabled.

    Enable with either:
        pytest -m integration           (explicit marker selection)
        INTEGRATION_TESTS=1 pytest      (env var)
    """
    run_integration = os.environ.get("INTEGRATION_TESTS", "0") == "1"

    # If the user explicitly selected -m integration, don't skip
    keyword_expr = config.getoption("-m", default="")
    if "integration" in keyword_expr:
        return

    if run_integration:
        return

    skip_integration = pytest.mark.skip(reason="Integration tests disabled (set INTEGRATION_TESTS=1 or use -m integration)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def client():
    return TestClient(app)
