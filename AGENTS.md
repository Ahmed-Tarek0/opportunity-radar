# AGENTS.md — Development and Agent Guidelines

## 1. Project Summary & Identity
**Opportunity Radar** is a modular monolith application built with Python 3.11+, Streamlit, Pydantic v2, and SQLAlchemy 2.x.
Its primary mission is to extract structured skills, experiences, and target roles from software engineering CVs (PDF/DOCX/TXT), query multiple real-time and ATS job sources without requiring full scrapers or private authenticated APIs, deterministically match candidates against retrieved opportunities using a explainable multi-factor scoring rubric, and present high-confidence results with strict freshness and location integrity.

---

## 2. Architecture Invariants

1. **Strict Layer Boundary & Dependency Flow**:
   - `ui/` (Streamlit Presentation) $\rightarrow$ `services/` (Application Services) $\rightarrow$ Domain (`matching/`, `job_processing/`, `cv_parser/`) $\rightarrow$ Infrastructure (`db/`, `sources/`, `llm/`).
   - Domain logic and business rules must never import from `ui/`.
   - Presentation layers must never directly access raw database sessions or third-party HTTP clients; all workflows route through service interfaces (`SearchWorkflowService`, `ProfileService`, etc.).

2. **No Direct LLM Calls from Presentation / Domain**:
   - Every LLM invocation must route through the `llm/` provider abstraction (`BaseLLMProvider`, `GeminiProvider`, `OpenAIProvider`, `create_llm_provider`).
   - All prompts, retries, and JSON repair loops reside exclusively within the LLM abstraction or designated extraction adapters.

3. **Failure Isolation (Graceful Degradation)**:
   - Each job source adapter (`sources/`) operates as an isolated worker.
   - If a source encounters network errors, rate limits, HTML structure changes, or parsing errors, it logs the failure and yields a `SourceRunResult` with status `failed` or `partial`.
   - A failure in one source (e.g., LinkedIn or WUZZUF) **must never halt or abort other sources**.

4. **Honest Diagnostics**:
   - Every source reports its genuine operational status: `success`, `partial`, `disabled`, `not_configured`, or `failed`.
   - Missing credentials or parameters (e.g. missing `ADZUNA_APP_ID`, missing `GREENHOUSE_BOARD_SLUGS`) are classified as `not_configured`, **never faked, mocked as working, or masked as empty success**.

5. **Zero Fabrication**:
   - Never invent jobs, posting dates, companies, or URLs.
   - Demo mode data is strictly partitioned and explicitly marked with `is_demo = True`. Synthetic test fixtures must never blend with live job listings without clear distinction.

6. **Date & Time Integrity**:
   - `posted_at` is the verified, original posting timestamp provided by the source.
   - Never substitute `fetched_at` or `first_seen_at` in place of `posted_at`. If a source omits a timestamp, `posted_at` remains `None` with `date_status = unknown`.
   - All datetime objects are parsed to UTC and stored as ISO 8601 strings or UTC datetimes in persistence. Rendering and filtering adhere to the candidate's timezone (`Africa/Cairo` by default).

7. **Privacy & Security Boundaries**:
   - Raw CV file bytes or raw extracted resumes are **never stored** in the database or serialized to disk.
   - Only a cryptographic SHA-256 hash (`source_file_hash`) and the validated Pydantic model (`CandidateProfile`) are retained.
   - Prompt injection guardrails: Untrusted CV and job text are treated as passive text payloads and shielded with explicit delimiters and defensive system prompts.

---

## 3. Coding & Test Conventions

- **Type Annotations**: All public functions, class methods, and models require strict type hints. Code passes `ruff` and standard type checkers without ambiguous `Any` when concrete types are expressible.
- **Data Validation**: Use Pydantic v2 schemas (`BaseModel` with `ConfigDict(frozen=...)` where applicable). Use SQLAlchemy 2.x mapped classes (`Mapped`, `mapped_column`, or declarative `Column` patterns).
- **Paths & Filesystem**: Always use `pathlib.Path`. Never use `os.path`.
- **Time Handling**: Store UTC timestamps (`datetime.now(timezone.utc)`). Never use naive datetimes (`datetime.now()`).
- **HTTP Clients**: Use `httpx.Client` or `httpx.AsyncClient` with explicit timeouts, connection pools, and browser-like user agents. Close clients cleanly or use context managers.
- **Testing Standard**: Tests reside in `tests/` split into `unit/` and `integration/`. Test fixtures and mock responses use `respx` or `unittest.mock`. Tests must never make real live external network calls.

---

## 4. Exact CLI Commands

### Activate Virtual Environment
```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.\.venv\Scripts\activate.bat

# Linux / macOS
source .venv/bin/activate
```

### Install Dependencies
```bash
pip install -e ".[dev]"
```

### Initialize Database
```bash
python scripts/init_db.py
```

### Seed Demo Fixtures
```bash
python scripts/seed_demo_data.py
```

### Run Source Diagnostics
```bash
python scripts/check_sources.py
```

### Run Tests
```bash
python -m pytest tests/ -v
```

### Run Linter & Formatter Check
```bash
ruff check src tests
ruff format --check src tests
```

### Launch Streamlit Application
```bash
streamlit run app.py
```
