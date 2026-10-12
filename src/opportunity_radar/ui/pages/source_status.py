"""Source Status page."""
from __future__ import annotations

import streamlit as st

from opportunity_radar.config import get_settings
from opportunity_radar.ui.common import render_demo_banner, source_status_badge
from opportunity_radar.ui.state import init_session_state


def main():
    settings = get_settings()
    init_session_state()
    render_demo_banner()

    st.markdown("## 📡 Source Status & Settings")
    st.divider()

    # LLM info
    st.markdown("### 🤖 AI Configuration")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Provider:** {settings.llm_provider}")
        if settings.llm_provider == "gemini":
            st.markdown(f"**Model:** `{settings.gemini_model}`")
            status = "✅ Configured" if settings.gemini_api_key else "❌ API key not set"
            st.markdown(f"**Status:** {status}")
        elif settings.llm_provider == "openai":
            st.markdown(f"**Model:** `{settings.openai_model}`")
            status = "✅ Configured" if settings.openai_api_key else "❌ API key not set"
            st.markdown(f"**Status:** {status}")
    with col2:
        if not settings.has_llm:
            st.warning("No LLM configured. Profile extraction uses heuristics only. Set GEMINI_API_KEY or OPENAI_API_KEY.")
        st.markdown(f"**Semantic matching:** {'✅ Enabled' if settings.enable_semantic_matching else '⚪ Disabled'}")
        st.markdown(f"**Demo Mode:** {'🎭 ON' if settings.demo_mode else '🔴 OFF (live)'}")

    st.divider()
    st.markdown("### 📡 Job Sources")

    from opportunity_radar.sources.registry import build_registry
    registry = build_registry()

    # Get latest source results if available
    last_results = {r.source_name: r for r in st.session_state.get("source_results", [])}

    for source in registry.all_sources():
        with st.expander(f"{source.display_name} ({source.source_name})", expanded=True):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                if not source.is_enabled():
                    st.markdown(source_status_badge("disabled"))
                elif not source.is_configured():
                    st.markdown(source_status_badge("not_configured"))
                else:
                    st.markdown(source_status_badge("success"))

            with col2:
                if source.source_name in last_results:
                    r = last_results[source.source_name]
                    st.markdown(f"Last run: **{r.jobs_fetched}** jobs in **{r.duration_seconds:.1f}s**")
                    if r.message:
                        st.caption(r.message)
                else:
                    st.caption("No search run yet.")

            with col3:
                if not source.is_configured() or not source.is_enabled():
                    st.markdown(source_status_badge("disabled" if not source.is_enabled() else "not_configured"))

    st.divider()
    st.markdown("### ⚙️ Configuration")
    st.info(
        "Configuration is loaded from the `.env` file. "
        "Edit `.env` and restart the app to apply changes. "
        "Secrets are never displayed here."
    )
    st.markdown(f"- **App env:** `{settings.app_env}`")
    st.markdown(f"- **Database:** `{settings.database_url.split('://')[0]}` (type only)")
    st.markdown(f"- **Lookback:** {settings.job_lookback_days} days")
    st.markdown(f"- **Timeout:** {settings.request_timeout_seconds}s per source")
    st.markdown(f"- **Max pages/source:** {settings.max_pages_per_source}")
    st.markdown(f"- **Concurrent sources:** {settings.max_concurrent_source_requests}")


main()
