import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(scope="session")
def demo_settings():
    """Settings configured for testing with demo mode."""
    import os
    os.environ["DEMO_MODE"] = "true"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["LLM_PROVIDER"] = "none"
    from opportunity_radar.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest.fixture(scope="function")
def db_session(demo_settings):
    """In-memory SQLite session for tests."""
    import opportunity_radar.db.session as sess_mod
    from opportunity_radar.db.session import get_session, init_db
    # Reset engine for test isolation
    sess_mod._engine = None
    sess_mod._SessionFactory = None
    init_db()
    with get_session() as session:
        yield session
