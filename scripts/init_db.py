#!/usr/bin/env python
"""Initialize the database by creating all tables."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from opportunity_radar.logging_config import setup_logging
from opportunity_radar.db.session import init_db

if __name__ == "__main__":
    setup_logging()
    init_db()
    print("Database initialized successfully.")
