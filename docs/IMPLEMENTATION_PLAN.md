# Implementation Plan: Opportunity Radar

## 1. Project Mission & Technical Vision
Opportunity Radar is an intelligent job intelligence and recommendation platform designed to ingest candidate resumes (PDF, DOCX, TXT), parse verifiable skills and background data, search across public and semi-structured job feeds (LinkedIn Guest, WUZZUF, Remote OK, Greenhouse, Lever, Adzuna), deduplicate across sources, and score opportunities using a transparent, multi-factor deterministic matching algorithm.

---

## 2. Technical Choices & Rationales

| Layer / Technology | Choice | Rationale |
| :--- | :--- | :--- |
| **Language & Runtime** | Python 3.11+ | Enhanced exception groups, performance improvements, static typing features. |
| **User Interface** | Streamlit (multipage) | Fast iteration, interactive UI widgets, seamless integration with data structures. |
| **Data Validation** | Pydantic v2 | High-performance Rust-backed validation, JSON schema serialization, strict typing. |
| **Persistence** | SQLAlchemy 2.x + SQLite (default) / PostgreSQL | Modern 2.0 select style, full relationship cascade management, JSON column support. |
| **HTTP Client** | `httpx` | Modern, clean connection pooling, sync & async support, customizable headers. |
| **Fuzzy Matching** | `rapidfuzz` | Ultra-fast C++ optimized token sort and Levenshtein metrics for skill normalization. |
| **Document Parsers** | `PyMuPDF` (fitz) + `python-docx` | High fidelity text extraction without heavy OCR dependencies. |
| **LLM Integration** | Google Gemini (`google-genai`) & OpenAI (`openai`) | Flexible multi-provider support with schema repair fallbacks. |

---

## 3. Seven Implementation Phases

### Phase 1: Foundation & Data Architecture
- [x] Configure project directory structure, dependencies in `pyproject.toml`, and `.env.example`.
- [x] Establish unified logging configuration (`logging_config.py`) with sanitized log boundaries.
- [x] Define Pydantic domain schemas (`CandidateProfile`, `NormalizedJob`, `MatchResult`, `SourceRunResult`).
- [x] Define SQLAlchemy 2.x ORM models (`CandidateProfileModel`, `JobModel`, `JobMatchModel`, `SavedJobModel`, `SearchRunModel`).
- [x] Implement database initialization and session management (`db/session.py`, `scripts/init_db.py`).

### Phase 2: CV Parsing & Profile Extraction
- [x] Implement file validation (`file_validation.py`) for PDF, DOCX, and TXT with SHA-256 fingerprinting.
- [x] Implement text extractors (`text_extractor.py`) using `PyMuPDF` and `python-docx`.
- [x] Implement LLM-backed structured extraction (`profile_extractor.py`) with strict prompt isolation.
- [x] Implement rule-based fallback extractor for zero-LLM local operation.
- [x] Unit test CV validation, text extraction, and schema compliance (`test_cv_parser.py`).

### Phase 3: Source Adapters & Acquisition Engine
- [x] Define `JobSource` abstract base class and `SourceRegistry` pattern (`sources/base.py`, `sources/registry.py`).
- [x] Implement fixture-based `DemoSource` loaded from `data/demo_jobs.json`.
- [x] Implement LinkedIn guest search adapter (`sources/linkedin/`).
- [x] Implement WUZZUF Egypt job board adapter (`sources/wuzzuf/`).
- [x] Implement Remote OK worldwide remote API adapter (`sources/remoteok/`).
- [x] Implement Greenhouse Job Board v1 API adapter (`sources/greenhouse/`).
- [x] Implement Lever Postings v0 API adapter (`sources/lever/`).
- [x] Implement Adzuna Developer API adapter (`sources/adzuna/`).
- [x] Implement CLI source diagnostics script (`scripts/check_sources.py`).

### Phase 4: Job Processing & Normalization Pipeline
- [x] Implement work mode and remote eligibility normalizer (`job_processing/normalizer.py`).
- [x] Implement location rules and Egypt/Worldwide categorization (`job_processing/location_rules.py`).
- [x] Implement posting date parser with UTC conversion and Cairo timezone formatting (`job_processing/freshness.py`).
- [x] Implement job deduplicator (`job_processing/deduplicator.py`) using canonical URLs and fuzzy title/company matching.
- [x] Unit test deduplication and freshness logic (`test_deduplication.py`, `test_freshness.py`).

### Phase 5: Matching & Scoring Engine
- [x] Implement taxonomy-based skill alias normalizer (`matching/skill_normalizer.py`).
- [x] Implement deterministic multi-factor scorer (`matching/scorer.py`):
  - Skill overlap: 40%
  - Experience level alignment: 25%
  - Title & role relevance: 20%
  - Work mode & location preference: 15%
- [x] Implement automated search query generator (`matching/query_generator.py`).
- [x] Support optional semantic embedding similarity via Gemini / OpenAI embedding providers.
- [x] Unit test scoring permutations and deterministic calculation (`test_matching.py`).

### Phase 6: Orchestration Services & Persistence Workflows
- [x] Implement `ProfileService` for CV processing, hashing, and demo profile provisioning.
- [x] Implement `SearchWorkflowService` for parallel/isolated multi-source execution, deduplication, scoring, and run logging.
- [x] Implement demo data seeding script (`scripts/seed_demo_data.py`).
- [x] Support SQLite database transactions with foreign key cascades and indexed queries.

### Phase 7: Presentation Layer & UI Experience
- [x] Build multi-page Streamlit layout (`app.py`, `ui/pages/home.py`, `ui/pages/profile.py`, `ui/pages/discover_jobs.py`, `ui/pages/saved_jobs.py`, `ui/pages/source_status.py`).
- [x] Implement interactive profile confirmation screen with skill editing.
- [x] Implement job discovery view with filters (search query, min score, source filter, remote/hybrid).
- [x] Implement expandable job cards with score breakdown, citations, and apply links.
- [x] Implement saved jobs management and CSV export functionality.
- [x] Implement real-time source status health dashboard.

---

## 4. Risk Matrix & Mitigations

| Identified Risk | Impact | Likelihood | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **HTML Changes in Public Endpoints** (LinkedIn / WUZZUF) | Medium | High | Isolated execution; failure in scrapers generates warnings rather than crashing the run. Strict schema fallback. |
| **LLM Output Non-Compliance / JSON Malformation** | High | Medium | Dual-layer regex JSON extractor, schema validation with Pydantic, and automatic deterministic regex fallback. |
| **Missing API Credentials** | Low | High | Sources detect unconfigured states upfront (`not_configured`) without executing HTTP requests or fabricating responses. |
| **Data Privacy & PII Leakage** | High | Low | Raw CV byte streams are discarded immediately post-extraction; only cryptographically hashed references are persisted. |
| **Date Timezone Inaccuracies** | Medium | Medium | Strict UTC storage policy; all incoming formats parsed and converted to UTC, rendered in `Africa/Cairo`. |
