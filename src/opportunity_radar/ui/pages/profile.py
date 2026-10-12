"""CV Upload and Profile Review page."""
from __future__ import annotations

import streamlit as st

from opportunity_radar.config import get_settings
from opportunity_radar.exceptions import CVParsingError, CVValidationError
from opportunity_radar.ui.common import render_demo_banner, render_error
from opportunity_radar.ui.state import get_profile, init_session_state, set_profile


def main():
    settings = get_settings()
    init_session_state()
    render_demo_banner()

    st.markdown("## 📄 CV Upload & Profile Review")
    st.caption("Upload your CV to extract a structured professional profile.")
    st.divider()

    profile = get_profile()

    # Upload section
    if not profile:
        _render_upload_section(settings)
    else:
        _render_profile_view(profile)


def _render_upload_section(settings):
    col1, col2 = st.columns([2, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Upload your CV (PDF or DOCX)",
            type=["pdf", "docx"],
            help=f"Maximum file size: {settings.cv_max_size_mb} MB",
        )

        if uploaded_file is not None:
            with st.spinner("Parsing CV..."):
                try:
                    from opportunity_radar.llm.factory import create_llm_provider
                    from opportunity_radar.services.profile_service import ProfileService

                    llm = create_llm_provider(settings)
                    service = ProfileService(llm_provider=llm)

                    file_bytes = uploaded_file.read()
                    profile, file_hash = service.process_upload(
                        filename=uploaded_file.name,
                        file_bytes=file_bytes,
                        content_type=uploaded_file.type,
                    )
                    set_profile(profile)

                    if settings.has_llm:
                        st.success("✅ CV parsed successfully using LLM!")
                    else:
                        st.warning(
                            "CV parsed using heuristics (no LLM configured). "
                            "Results may be less accurate. Please review and edit."
                        )
                    st.rerun()

                except CVValidationError as e:
                    render_error(str(e))
                except CVParsingError as e:
                    render_error(f"Could not parse CV: {e}")
                except Exception as e:
                    render_error(f"Unexpected error: {type(e).__name__}: {e}")

    with col2:
        st.markdown("### Or use a Demo Profile")
        st.markdown("Don't have a CV handy? Use our synthetic demo profile to explore the app.")
        if st.button("Load Demo Profile", use_container_width=True):
            from opportunity_radar.services.profile_service import ProfileService
            service = ProfileService()
            demo = service.get_demo_profile()
            set_profile(demo)
            st.rerun()

        st.divider()
        st.markdown("**Privacy Note:**")
        st.caption(
            "Your CV text is processed in memory and not stored. "
            "Only the structured profile is saved locally. "
            "If using a cloud LLM, CV text is sent to the configured provider."
        )


def _render_profile_view(profile):
    # Profile loaded banner
    if profile.is_demo:
        st.info("🎭 Viewing DEMO profile. Upload your CV to replace it.")

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### {profile.headline or profile.primary_title()}")
        if profile.summary:
            st.markdown(profile.summary)
    with col2:
        st.metric("Confidence", f"{int(profile.profile_confidence * 100)}%")
        st.metric("Seniority", profile.seniority_estimate.value.title())
        if profile.years_experience_estimate:
            st.metric("Est. Experience", f"{profile.years_experience_estimate:.1f} yrs")

    # Warnings
    for warning in profile.fields_needing_confirmation:
        if len(warning.split()) <= 2 and ("_" in warning or warning.islower()):
            field_name = warning.replace("_", " ").title()
            st.info(f"ℹ️ Note: **{field_name}** was not explicitly found in your CV and is currently unassigned.")
        else:
            st.warning(f"⚠️ {warning}")

    st.divider()

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Skills", "Target Roles", "Experience", "Education", "Preferences"])

    with tab1:
        st.markdown("#### Skills Extracted from CV")
        if profile.skills:
            cols = st.columns(3)
            for i, skill in enumerate(profile.skills):
                with cols[i % 3]:
                    confidence_pct = int(skill.confidence * 100)
                    evidence_label = skill.evidence_type.value if skill.evidence_type else ""
                    st.markdown(
                        f"**{skill.original}** `{confidence_pct}%`  \n"
                        f"*{evidence_label}*"
                    )
        else:
            st.info("No skills extracted. Upload a more detailed CV or edit manually.")

    with tab2:
        st.markdown("#### Suggested Job Titles")
        st.caption("These are used to generate search queries. Edit to refine your search.")
        if profile.target_titles:
            for title in profile.target_titles:
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**{title.title}**")
                    if title.rationale:
                        st.caption(title.rationale)
                with col_b:
                    st.progress(title.confidence, text=f"{int(title.confidence*100)}%")
        else:
            st.info("No target titles extracted. Add some manually.")

    with tab3:
        st.markdown("#### Work Experience")
        if profile.experiences:
            for exp in profile.experiences:
                with st.expander(f"{exp.title} @ {exp.employer or 'Unknown Company'}"):
                    if exp.start_date or exp.end_date:
                        st.caption(f"{exp.start_date or '?'} → {exp.end_date or 'present'}")
                    if exp.description:
                        st.markdown(exp.description)
                    if exp.technologies:
                        st.markdown("**Technologies:** " + ", ".join(exp.technologies))
        else:
            st.info("No work experience extracted.")

    with tab4:
        st.markdown("#### Education")
        if profile.education:
            for edu in profile.education:
                st.markdown(f"**{edu.degree or 'Degree'}** — {edu.institution or 'Institution'}")
                if edu.graduation_year:
                    st.caption(f"Graduated: {edu.graduation_year}")
        else:
            st.info("No education information extracted.")

    with tab5:
        st.markdown("#### Location & Work Preferences")
        pref = profile.location_preference
        emp = profile.employment_preferences

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Location Preferences**")
            st.markdown(f"- Egypt roles: {'✅' if pref.include_egypt else '❌'}")
            st.markdown(f"- Worldwide remote: {'✅' if pref.include_worldwide_remote else '❌'}")
        with col2:
            st.markdown("**Work Arrangement**")
            st.markdown(f"- Remote: {'✅' if emp.remote else '❌'}")
            st.markdown(f"- Hybrid: {'✅' if emp.hybrid else '❌'}")
            st.markdown(f"- On-site: {'✅' if emp.on_site else '❌'}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Find Matching Jobs", type="primary", use_container_width=True):
            st.switch_page("src/opportunity_radar/ui/pages/discover_jobs.py")
    with col2:
        if st.button("🔄 Upload Different CV", use_container_width=True):
            set_profile(None)
            st.session_state["search_results"] = []
            st.session_state["search_matches"] = []
            st.rerun()


main()
