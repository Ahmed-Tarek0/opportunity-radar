"""Home page for Opportunity Radar."""
from __future__ import annotations

import streamlit as st

from opportunity_radar.config import get_settings
from opportunity_radar.ui.common import render_demo_banner
from opportunity_radar.ui.state import get_profile, get_saved_jobs, get_search_results


def main():
    settings = get_settings()

    render_demo_banner()

    # Hero section
    st.markdown("""
    # 🎯 Opportunity Radar
    ### Discover jobs that match your CV — powered by AI matching
    """)

    st.markdown("""
    Opportunity Radar analyzes your CV to extract your skills and experience, 
    then searches multiple job sources to find opportunities that genuinely match your profile.
    Results are ranked transparently with clear explanations of why each job is a good fit.
    """)

    st.divider()

    # Stats row
    profile = get_profile()
    jobs = get_search_results()
    saved = get_saved_jobs()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Profile",
            "✅ Loaded" if profile else "❌ Not loaded",
            help="Upload your CV to get started"
        )
    with col2:
        st.metric(
            "Jobs Found",
            len(jobs) if jobs else 0,
            help="Jobs from the last search run"
        )
    with col3:
        strong_matches = sum(1 for m in st.session_state.get("search_matches", []) if m.match_score >= 70)
        st.metric(
            "Strong Matches",
            strong_matches,
            help="Jobs with ≥70 match score"
        )
    with col4:
        st.metric(
            "Saved Jobs",
            len(saved),
            help="Jobs you have saved"
        )

    st.divider()

    # CTAs
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📄 Upload Your CV")
        st.markdown("Upload a PDF or DOCX file to extract your professional profile and start finding matching jobs.")
        if st.button("Upload CV & Build Profile", type="primary", use_container_width=True):
            st.switch_page("src/opportunity_radar/ui/pages/profile.py")

    with col2:
        st.markdown("### 🔍 Find Jobs")
        if profile:
            st.markdown(f"Profile loaded: **{profile.headline or profile.primary_title()}**. Ready to search!")
            if st.button("Discover Matching Jobs", type="primary", use_container_width=True):
                st.switch_page("src/opportunity_radar/ui/pages/discover_jobs.py")
        else:
            st.markdown("Upload your CV first, or use the demo profile to explore the app.")
            if st.button("Use Demo Profile", use_container_width=True):
                from opportunity_radar.services.profile_service import ProfileService
                service = ProfileService()
                demo_profile = service.get_demo_profile()
                from opportunity_radar.ui.state import set_profile
                set_profile(demo_profile)
                st.success("Demo profile loaded! Now try Discover Jobs.")
                st.rerun()

    st.divider()

    # Features
    st.markdown("### What Opportunity Radar Does")

    feat_col1, feat_col2, feat_col3 = st.columns(3)

    with feat_col1:
        st.markdown("""**🤖 Smart CV Analysis**  
        Extracts your skills, experience, and target roles using AI. 
        Review and edit before searching.""")

    with feat_col2:
        st.markdown("""**🔎 Multi-Source Search**  
        Searches LinkedIn, WUZZUF, Remote OK, and other sources. 
        Normalizes and deduplicates across all sources.""")

    with feat_col3:
        st.markdown("""**📊 Transparent Matching**  
        Each job gets an explainable score with skill gaps, 
        seniority alignment, and evidence from your CV.""")

    # Mode indicator
    st.divider()
    mode_text = "🎭 Demo Mode (synthetic data)" if settings.demo_mode else "🔴 Live Mode (real job sources)"
    llm_text = f"🤖 LLM: {settings.llm_provider} ({settings.gemini_model if settings.llm_provider == 'gemini' else settings.openai_model})" if settings.has_llm else "🤖 LLM: Not configured (using heuristics)"
    st.caption(f"{mode_text} | {llm_text} | DB: {settings.database_url.split('/')[-1]}")


main()
