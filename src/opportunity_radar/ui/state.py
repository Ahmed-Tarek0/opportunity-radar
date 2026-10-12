import json
from pathlib import Path
import streamlit as st

from ..schemas.job import NormalizedJob
from ..schemas.matching import MatchResult
from ..schemas.profile import CandidateProfile

ACTIVE_PROFILE_PATH = Path(__file__).resolve().parents[3] / "data" / "active_profile.json"
LAST_SEARCH_PATH = Path(__file__).resolve().parents[3] / "data" / "last_search.json"
SAVED_JOBS_PATH = Path(__file__).resolve().parents[3] / "data" / "saved_jobs.json"

SESSION_KEYS = [
    "profile",
    "search_results",
    "search_matches",
    "source_results",
    "saved_job_ids",
    "saved_jobs_store",
    "search_run_id",
    "search_warnings",
    "search_counts",
    "last_search_time",
    "upload_error",
    "current_page",
]


def init_session_state() -> None:
    """Initialize all session state keys with defaults."""
    defaults = {
        "profile": None,
        "search_results": [],
        "search_matches": [],
        "source_results": [],
        "saved_job_ids": set(),
        "saved_jobs_store": {},  # job_id -> NormalizedJob dict
        "search_run_id": None,
        "search_warnings": [],
        "search_counts": {},
        "last_search_time": None,
        "upload_error": None,
        "current_page": "home",
        "selected_lookback_days": 30,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # Auto-restore profile from disk if not in session state
    if st.session_state.get("profile") is None and ACTIVE_PROFILE_PATH.exists():
        try:
            raw_text = ACTIVE_PROFILE_PATH.read_text(encoding="utf-8")
            st.session_state["profile"] = CandidateProfile.model_validate_json(raw_text)
        except Exception:
            pass

    # Auto-restore saved jobs from disk
    if SAVED_JOBS_PATH.exists():
        try:
            saved_data = json.loads(SAVED_JOBS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved_data, dict):
                st.session_state["saved_jobs_store"] = saved_data
                st.session_state["saved_job_ids"] = set(saved_data.keys())
        except Exception:
            pass

    # Auto-restore last search results from disk if empty
    if not st.session_state.get("search_results") and LAST_SEARCH_PATH.exists():
        try:
            data = json.loads(LAST_SEARCH_PATH.read_text(encoding="utf-8"))
            st.session_state["search_results"] = [NormalizedJob.model_validate(j) for j in data.get("jobs", [])]
            st.session_state["search_matches"] = [MatchResult.model_validate(m) for m in data.get("matches", [])]
            if "lookback_days" in data:
                st.session_state["selected_lookback_days"] = data["lookback_days"]
        except Exception:
            pass


def get_profile() -> CandidateProfile | None:
    prof = st.session_state.get("profile")
    if prof is None and ACTIVE_PROFILE_PATH.exists():
        try:
            raw_text = ACTIVE_PROFILE_PATH.read_text(encoding="utf-8")
            prof = CandidateProfile.model_validate_json(raw_text)
            st.session_state["profile"] = prof
        except Exception:
            pass
    return prof


def set_profile(profile: CandidateProfile | None) -> None:
    st.session_state["profile"] = profile
    if profile is not None:
        try:
            ACTIVE_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
            ACTIVE_PROFILE_PATH.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        except Exception:
            pass
    else:
        if ACTIVE_PROFILE_PATH.exists():
            try:
                ACTIVE_PROFILE_PATH.unlink()
            except Exception:
                pass


def get_search_results() -> list[NormalizedJob]:
    return st.session_state.get("search_results", [])


def set_search_results(jobs: list[NormalizedJob], matches: list[MatchResult], lookback_days: int = 30) -> None:
    st.session_state["search_results"] = jobs
    st.session_state["search_matches"] = matches
    st.session_state["selected_lookback_days"] = lookback_days
    try:
        LAST_SEARCH_PATH.parent.mkdir(parents=True, exist_ok=True)
        dump_data = {
            "jobs": [j.model_dump(mode="json") for j in jobs],
            "matches": [m.model_dump(mode="json") for m in matches],
            "lookback_days": lookback_days,
        }
        LAST_SEARCH_PATH.write_text(json.dumps(dump_data), encoding="utf-8")
    except Exception:
        pass


def get_matches() -> list[MatchResult]:
    return st.session_state.get("search_matches", [])


def toggle_saved_job(job_id: str, job: NormalizedJob | None = None) -> bool:
    """Toggle a saved job. Returns True if now saved, False if removed."""
    saved_ids = st.session_state.get("saved_job_ids", set())
    saved_store = st.session_state.get("saved_jobs_store", {})

    if job_id in saved_ids:
        saved_ids.discard(job_id)
        saved_store.pop(job_id, None)
        result = False
    else:
        saved_ids.add(job_id)
        # Find job object if not passed
        if job is None:
            all_jobs = get_search_results()
            found = next((j for j in all_jobs if str(j.id) == job_id), None)
            if found:
                job = found
        if job is not None:
            saved_store[job_id] = job.model_dump(mode="json")
        result = True

    st.session_state["saved_job_ids"] = saved_ids
    st.session_state["saved_jobs_store"] = saved_store

    # Persist to disk
    try:
        SAVED_JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SAVED_JOBS_PATH.write_text(json.dumps(saved_store, indent=2), encoding="utf-8")
    except Exception:
        pass

    return result


def is_saved(job_id: str) -> bool:
    return job_id in st.session_state.get("saved_job_ids", set())


def get_saved_jobs() -> list[NormalizedJob]:
    saved_store = st.session_state.get("saved_jobs_store", {})
    if saved_store:
        jobs = []
        for j_data in saved_store.values():
            try:
                jobs.append(NormalizedJob.model_validate(j_data))
            except Exception:
                pass
        return jobs
    # Fallback to search results match
    saved_ids = st.session_state.get("saved_job_ids", set())
    all_jobs = get_search_results()
    return [j for j in all_jobs if str(j.id) in saved_ids]
