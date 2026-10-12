from __future__ import annotations

import streamlit as st

from ..config import get_settings


def render_demo_banner() -> None:
    """Render a visible Demo Mode banner."""
    settings = get_settings()
    if settings.demo_mode:
        st.warning(
            "🎭 **DEMO MODE** — Displaying synthetic example data. "
            "Set DEMO_MODE=false and configure API keys to search live job sources.",
            icon="⚠️",
        )


def render_page_header(title: str, subtitle: str = "") -> None:
    """Render a consistent page header."""
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


def render_error(message: str) -> None:
    """Render an error message."""
    st.error(f"❌ {message}")


def render_warning(message: str) -> None:
    """Render a warning message."""
    st.warning(f"⚠️ {message}")


def render_success(message: str) -> None:
    """Render a success message."""
    st.success(f"✅ {message}")


def render_info(message: str) -> None:
    """Render an info message."""
    st.info(f"ℹ️ {message}")


def source_status_badge(status: str) -> str:
    """Return a colored status badge string."""
    badges = {
        "success": "🟢 Active",
        "partial": "🟡 Partial",
        "disabled": "⚫ Disabled",
        "not_configured": "🔵 Not Configured",
        "failed": "🔴 Failed",
        "not_implemented": "⚪ Not Implemented",
    }
    return badges.get(status, f"❓ {status}")


def work_mode_badge(mode: str) -> str:
    badges = {
        "onsite": "🏢 On-site",
        "hybrid": "🔄 Hybrid",
        "remote": "🌐 Remote",
        "unknown": "❓ Unknown",
    }
    return badges.get(mode, mode)


def score_color(score: int) -> str:
    """Return color based on match score."""
    if score >= 70:
        return "#27AE60"  # green
    elif score >= 50:
        return "#F39C12"  # orange
    else:
        return "#E74C3C"  # red
