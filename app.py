"""Opportunity Radar — Main Streamlit Application Entry Point."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from opportunity_radar.config import get_settings
from opportunity_radar.logging_config import setup_logging
from opportunity_radar.db.session import init_db
from opportunity_radar.ui.state import init_session_state
from opportunity_radar.ui.common import render_demo_banner


def main() -> None:
    # Setup
    setup_logging()
    settings = get_settings()

    # Initialize database
    try:
        init_db()
    except Exception as e:
        st.error(f"Database initialization failed: {e}")
        return

    # Page config
    st.set_page_config(
        page_title="Opportunity Radar",
        page_icon="🎯",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Session state
    init_session_state()

    # Custom CSS
    st.markdown("""
    <style>
    .stApp { background-color: #0F1117; }
    .main .block-container { padding-top: 2rem; max-width: 1200px; }
    div[data-testid="metric-container"] { background: #1E2130; border-radius: 8px; padding: 8px; }
    .job-card { background: #1E2130; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #4A90E2; }
    .score-badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 14px; }
    </style>
    """, unsafe_allow_html=True)

    # Navigation
    home_page = st.Page("src/opportunity_radar/ui/pages/home.py", title="Home", icon="🏠")
    profile_page = st.Page("src/opportunity_radar/ui/pages/profile.py", title="CV & Profile", icon="📄")
    discover_page = st.Page("src/opportunity_radar/ui/pages/discover_jobs.py", title="Discover Jobs", icon="🔍")
    saved_page = st.Page("src/opportunity_radar/ui/pages/saved_jobs.py", title="Saved Jobs", icon="⭐")
    pg = st.navigation([
        home_page, profile_page, discover_page, saved_page
    ])
    pg.run()


if __name__ == "__main__" or True:
    main()
