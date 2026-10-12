"""Saved Jobs page."""
from __future__ import annotations

import csv
import io

import streamlit as st

from opportunity_radar.job_processing.freshness import format_posted_date_cairo
from opportunity_radar.ui.common import render_demo_banner, work_mode_badge
from opportunity_radar.ui.state import get_saved_jobs, init_session_state, toggle_saved_job


def main():
    init_session_state()
    render_demo_banner()

    st.markdown("## ⭐ Saved Jobs")
    st.divider()

    saved = get_saved_jobs()

    if not saved:
        st.info("No saved jobs yet. Use the ☆ button on job cards to save interesting roles.")
        if st.button("Browse Jobs"):
            st.switch_page("src/opportunity_radar/ui/pages/discover_jobs.py")
        return

    st.markdown(f"**{len(saved)}** saved job(s)")

    # Export
    if saved:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Title", "Company", "Location", "Work Mode", "Source", "Posted Date", "URL"])
        for job in saved:
            writer.writerow([
                job.title, job.company_name, job.location_text or "",
                job.work_mode.value, job.source_name,
                format_posted_date_cairo(job.posted_at) if job.posted_at else "Unknown",
                job.source_url or "",
            ])
        st.download_button(
            "📥 Export Saved Jobs CSV",
            data=output.getvalue().encode("utf-8"),
            file_name="saved_jobs.csv",
            mime="text/csv",
        )

    for job in saved:
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"### {job.title}")
            st.markdown(f"**{job.company_name}** · {job.location_text or ''} · {work_mode_badge(job.work_mode.value)}")
            st.caption(f"Source: {job.source_name.upper()} · {format_posted_date_cairo(job.posted_at) if job.posted_at else 'Date unknown'}")
            if job.apply_url or job.source_url:
                label = "🔗 Apply (Demo Placeholder) →" if job.is_demo else "🔗 Apply →"
                st.markdown(f"[{label}]({job.apply_url or job.source_url})")
        with col2:
            if st.button("Remove", key=f"unsave_{job.id}"):
                toggle_saved_job(str(job.id))
                st.rerun()
        st.markdown("---")


main()
