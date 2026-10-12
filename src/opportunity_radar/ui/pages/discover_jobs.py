"""Discover Jobs page."""
from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

import streamlit as st

from opportunity_radar.config import get_settings
from opportunity_radar.job_processing.freshness import format_posted_date_cairo
from opportunity_radar.ui.common import render_demo_banner, score_color, work_mode_badge
from opportunity_radar.ui.state import (
    get_matches,
    get_profile,
    get_search_results,
    init_session_state,
    is_saved,
    set_search_results,
    toggle_saved_job,
)


def main():
    settings = get_settings()
    init_session_state()
    render_demo_banner()

    st.markdown("## 🔍 Discover Jobs")
    st.divider()

    profile = get_profile()

    if not profile:
        st.warning("No profile loaded. Please upload your CV first.")
        if st.button("Go to CV Upload"):
            st.switch_page("src/opportunity_radar/ui/pages/profile.py")
        return

    # Search controls
    with st.container():
        col1, col2 = st.columns([2, 3])
        with col1:
            st.markdown(f"**Searching for:** {profile.headline or profile.primary_title()}")
            include_undated = st.checkbox("Include undated jobs", value=True)
        with col2:
            lookback_labels = {
                7: "1 Week",
                14: "2 Weeks",
                21: "3 Weeks",
                30: "1 Month",
            }
            _saved_lb = st.session_state.get("selected_lookback_days", 30)
            _lb_options = [7, 14, 21, 30]
            _lb_index = _lb_options.index(_saved_lb) if _saved_lb in _lb_options else 3
            lookback = st.radio(
                "📅 Lookback period",
                _lb_options,
                index=_lb_index,
                format_func=lambda x: lookback_labels[x],
                horizontal=True,
            )

        if st.button("🔍 Find Jobs", type="primary", use_container_width=True):
            _run_search(profile, include_undated, lookback, settings)

    st.divider()

    # Source Diagnostics / Warnings
    warnings_list = st.session_state.get("search_warnings", [])
    if warnings_list:
        with st.expander("ℹ️ Source Diagnostics & Notices", expanded=False):
            for w in warnings_list:
                st.caption(f"• {w}")

    # Results
    jobs = get_search_results()
    matches = get_matches()

    if not jobs:
        if st.session_state.get("last_search_time"):
            st.info("No jobs found matching your criteria. Try expanding your lookback period or including undated jobs.")
        else:
            st.info("Click 'Find Jobs' to start searching.")
        return

    # Filters
    with st.expander("🔧 Filters & Sort", expanded=False):
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            min_score = st.slider("Minimum score", 0, 100, 40)
            sort_by = st.selectbox("Sort by", ["Match Score", "Posted Date", "Company"])
        with f_col2:
            work_modes = st.multiselect(
                "Work mode",
                ["onsite", "hybrid", "remote", "unknown"],
                default=["onsite", "hybrid", "remote", "unknown"],
            )
        with f_col3:
            sources_available = list(set(j.source_name for j in jobs))
            selected_sources = st.multiselect(
                "Sources",
                sources_available,
                default=sources_available,
            )

    # Build match lookup
    match_by_job_id = {str(m.job_id): m for m in matches}

    # Apply filters
    filtered_jobs = []
    filtered_matches = []
    for job in jobs:
        m = match_by_job_id.get(str(job.id))
        score = m.match_score if m else 0
        if score < min_score:
            continue
        if job.work_mode.value not in work_modes:
            continue
        if job.source_name not in selected_sources:
            continue
        filtered_jobs.append(job)
        filtered_matches.append(m)

    # Sort
    if sort_by == "Match Score":
        combined = sorted(zip(filtered_jobs, filtered_matches), key=lambda x: (x[1].match_score if x[1] else 0), reverse=True)
    elif sort_by == "Posted Date":
        combined = sorted(zip(filtered_jobs, filtered_matches), key=lambda x: x[0].posted_at or datetime.min.replace(tzinfo=UTC), reverse=True)
    else:
        combined = sorted(zip(filtered_jobs, filtered_matches), key=lambda x: x[0].company_name)

    if combined:
        filtered_jobs, filtered_matches = zip(*combined)
    else:
        filtered_jobs, filtered_matches = [], []

    st.markdown(f"**{len(filtered_jobs)}** jobs found")

    # CSV export
    if filtered_jobs:
        csv_data = _generate_csv(filtered_jobs, filtered_matches)
        st.download_button(
            "📥 Export to CSV",
            data=csv_data,
            file_name="opportunity_radar_results.csv",
            mime="text/csv",
        )

    # Render job cards
    for job, match in zip(filtered_jobs, filtered_matches):
        _render_job_card(job, match)


def _run_search(profile, include_undated: bool, lookback: int, settings):
    from opportunity_radar.services.search_workflow import SearchWorkflowService
    from opportunity_radar.sources.registry import build_registry

    progress_placeholder = st.empty()
    progress_bar = st.progress(0)
    stages = ["Generating queries", "Searching sources", "Normalizing", "Scoring", "Complete"]
    stage_idx = [0]

    def progress_callback(stage: str, detail: str):
        progress_placeholder.info(f"⏳ {stage}: {detail}")
        stage_idx[0] = min(stage_idx[0] + 1, len(stages))
        progress_bar.progress(stage_idx[0] / len(stages))

    registry = build_registry()
    service = SearchWorkflowService(registry, progress_callback=progress_callback)

    result = service.run(
        profile=profile,
        include_undated=include_undated,
        lookback_days=lookback,
        demo_mode=settings.demo_mode,
    )

    set_search_results(result.jobs, result.matches, lookback_days=lookback)
    st.session_state["source_results"] = result.source_results
    st.session_state["search_warnings"] = result.warnings
    st.session_state["search_counts"] = result.counts
    st.session_state["last_search_time"] = datetime.now(UTC)

    progress_placeholder.empty()
    progress_bar.empty()

    counts = result.counts
    st.success(
        f"✅ Found {counts.get('matched', 0)} matching jobs "
        f"({counts.get('fetched', 0)} fetched, "
        f"{counts.get('after_dedup', 0)} after dedup, "
        f"{counts.get('after_freshness', 0)} after date filter)"
    )
    st.rerun()


def _render_job_card(job, match):
    score = match.match_score if match else 0
    color = score_color(score)
    is_demo_label = " 🎭" if job.is_demo else ""
    posted_str = format_posted_date_cairo(job.posted_at) if job.posted_at else "Date unverified"
    date_icon = "📅" if job.date_status == "verified" else "❓"

    with st.container():
        col1, col2, col3 = st.columns([5, 2, 1])

        with col1:
            st.markdown(f"### {job.title}{is_demo_label}")
            st.markdown(f"**{job.company_name}** · {job.location_text or 'Location unknown'} · {work_mode_badge(job.work_mode.value)}")
            st.caption(f"{date_icon} {posted_str} · Source: {job.source_name.upper()}")

        with col2:
            st.markdown(
                f'<div style="text-align:center; background:{color}; color:white; '
                f'border-radius:50px; padding:8px; font-size:20px; font-weight:bold">'
                f'{score}/100</div>',
                unsafe_allow_html=True,
            )

        with col3:
            saved = is_saved(str(job.id))
            if st.button(
                "⭐" if saved else "☆",
                key=f"save_{job.id}",
                help="Unsave" if saved else "Save this job",
            ):
                toggle_saved_job(str(job.id), job=job)
                st.rerun()

        # Match details expander
        if match:
            with st.expander("📊 Match Details"):
                # Skills
                col_a, col_b = st.columns(2)
                has_any_skills = bool(match.matched_skills or match.missing_required_skills)
                with col_a:
                    if match.matched_skills:
                        st.markdown("**✅ Matched Skills**")
                        for skill in match.matched_skills[:8]:
                            st.markdown(f"  • `{skill}`")
                    elif not has_any_skills:
                        st.markdown("**ℹ️ Skills Analysis**")
                        st.caption("No specific skill keywords were listed in this job card. Matching is based on role, domain, and experience alignment.")
                with col_b:
                    if match.missing_required_skills:
                        st.markdown("**⚠️ Missing Required Skills**")
                        for skill in match.missing_required_skills[:8]:
                            st.markdown(f"  • `{skill}`")

                # Modern Score Breakdown
                st.markdown("---")
                st.markdown("#### 🎯 Score Breakdown")
                
                # Render components in styled 2x2 grid
                for comp in match.score_breakdown:
                    if comp.max_points <= 0:
                        continue
                    pct = comp.earned_points / comp.max_points if comp.max_points > 0 else 0
                    bar_color = "#10b981" if pct >= 0.75 else ("#3b82f6" if pct >= 0.5 else "#f59e0b")
                    
                    st.markdown(
                        f"""
                        <div style="background: rgba(255, 255, 255, 0.03); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; border-left: 4px solid {bar_color};">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <span style="font-weight: 600; font-size: 14px;">{comp.name}</span>
                                <span style="font-weight: 700; font-size: 14px; color: {bar_color};">{comp.earned_points:.0f} / {comp.max_points:.0f} pts</span>
                            </div>
                            <div style="font-size: 12px; opacity: 0.8; margin-top: 2px;">{comp.reason}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # Explanation
                if match.explanation:
                    st.markdown("**Analysis**")
                    for part in match.explanation.split(" | "):
                        st.markdown(f"  {part}")

                # Apply link
                if job.apply_url or job.source_url:
                    url = job.apply_url or job.source_url
                    if job.is_demo:
                        st.info(
                            "🎭 **Demo Listing**: This is synthetic test data using a placeholder link (`example.com`). "
                            "Set `DEMO_MODE=false` in `.env` to search and apply to live opportunities."
                        )
                        st.markdown(f"[🔗 View / Apply (Demo Placeholder: {url}) →]({url})")
                    else:
                        st.markdown(f"[🔗 View / Apply →]({url})")
                else:
                    st.warning("No application link available.")

        st.markdown("---")


def _generate_csv(jobs, matches) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Title", "Company", "Location", "Work Mode", "Source",
        "Match Score", "Posted Date", "Source URL", "Is Demo"
    ])

    match_by_job_id = {str(m.job_id): m for m in matches} if matches else {}

    for job in jobs:
        match = match_by_job_id.get(str(job.id))
        score = match.match_score if match else ""
        writer.writerow([
            job.title,
            job.company_name,
            job.location_text or "",
            job.work_mode.value,
            job.source_name,
            score,
            format_posted_date_cairo(job.posted_at) if job.posted_at else "Unknown",
            job.source_url or "",
            job.is_demo,
        ])

    return output.getvalue().encode("utf-8")


main()
