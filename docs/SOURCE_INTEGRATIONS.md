# Source Integrations Guide: Opportunity Radar

Opportunity Radar utilizes a decoupled adapter pattern (`JobSource`) managed by a central registry (`SourceRegistry`). This architecture guarantees failure isolation: if any single source suffers from network timeouts, anti-scraping challenges, or structure changes, the overall application pipeline continues unhindered.

---

## 1. Source Adapters Overview

### 1.1 Demo Source (`demo`)
- **Adapter Class**: `opportunity_radar.sources.demo.DemoSource`
- **Mechanism**: Loads synthetic job postings from `data/demo_jobs.json`.
- **Purpose**: Provides immediate end-to-end functionality without network connectivity or API credentials.
- **Constraints**:
  - Always marks `is_demo = True`.
  - Simulates remote worldwide roles, local Egypt roles, and distinct seniority levels to exercise all scoring branches.
- **Configuration**: Enabled when `DEMO_MODE=true` in `.env`. Requires `data/demo_jobs.json` to exist.

### 1.2 LinkedIn Guest Search (`linkedin`)
- **Adapter Class**: `opportunity_radar.sources.linkedin.client.LinkedInSource`
- **Mechanism**: Queries LinkedIn's public guest job search endpoint:
  ```http
  GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={query}&location={location}&start={start}
  ```
- **Parsing**: Extracts HTML job card snippets (`<li>`) using BeautifulSoup (`parser.py`). Extracts title, company name, location, posting date (`<time datetime="...">`), and canonical job URL.
- **Headers**: Rotates standard browser `User-Agent` and `Accept-Language` headers.
- **Limitations**:
  - Guest endpoints do not require authentication, but are subject to IP rate-limiting.
  - Returns paginated cards (approx. 10–25 per batch).
  - Deep descriptions are not always available without fetching individual job detail cards.

### 1.3 WUZZUF (`wuzzuf`)
- **Adapter Class**: `opportunity_radar.sources.wuzzuf.client.WuzzufSource`
- **Mechanism**: Scrapes WUZZUF's public search listing for software and engineering opportunities in Egypt:
  ```http
  GET https://wuzzuf.net/search/jobs/?q={query}&a=hpb
  ```
- **Parsing**: Parses HTML `<article>` cards and extracts job title, company name, city/governorate in Egypt, work type (`Full Time`, `Part Time`), and work arrangement tags (`Remote`, `Hybrid`, `On-site`).
- **Data Guarantees**:
  - Sets `country = "Egypt"` for all parsed jobs.
  - Extracts Egypt-specific cities (`Cairo`, `Giza`, `Alexandria`, `Maadi`, `New Cairo`).
- **Limitations**:
  - HTML structure updates on WUZZUF may require parser selector adjustments.

### 1.4 Remote OK (`remoteok`)
- **Adapter Class**: `opportunity_radar.sources.remoteok.client.RemoteOKSource`
- **Mechanism**: Ingests public JSON API provided by Remote OK:
  ```http
  GET https://remoteok.com/api
  ```
- **Parsing**: Skips the legal/header element (first record) and processes job objects.
  - Extracts `position`, `company`, `description`, `url`, `tags`, and epoch timestamps (`epoch`).
  - Converts epoch seconds directly to UTC datetimes.
  - Identifies salary mentions from tags and text fields.
- **Data Guarantees**:
  - All parsed jobs have `work_mode = WorkMode.remote`.
  - Determines `remote_eligibility = RemoteEligibility.worldwide` unless regional tags (`US only`, `Europe only`) are present.

### 1.5 Greenhouse ATS (`greenhouse`)
- **Adapter Class**: `opportunity_radar.sources.greenhouse.client.GreenhouseSource`
- **Mechanism**: Ingests the public Greenhouse Job Board v1 API for designated company board slugs:
  ```http
  GET https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true
  ```
- **Configuration**:
  - Requires comma-separated company slugs in `GREENHOUSE_BOARD_SLUGS` (e.g. `canonical,gitlab,automattic`).
- **Parsing**: Extracts native JSON attributes (`id`, `title`, `updated_at`, `absolute_url`, `content`, `location.name`).
- **Data Guarantees**:
  - Official ATS data with clean descriptions, exact URLs, and precise updated timestamps.
  - Status reports `not_configured` when `GREENHOUSE_BOARD_SLUGS` is empty.

### 1.6 Lever ATS (`lever`)
- **Adapter Class**: `opportunity_radar.sources.lever.client.LeverSource`
- **Mechanism**: Ingests the public Lever Postings API v0 for designated company slugs:
  ```http
  GET https://api.lever.co/v0/postings/{company_slug}?mode=json
  ```
- **Configuration**:
  - Requires comma-separated company slugs in `LEVER_COMPANY_SLUGS` (e.g. `palantir,netflix`).
- **Parsing**: Extracts `text` (title), `categories` (location, commitment, team), `hostedUrl`, `applyUrl`, `descriptionPlain`, and millisecond timestamps (`createdAt`).
- **Data Guarantees**:
  - Direct corporate job postings without intermediate scraper proxies.
  - Status reports `not_configured` when `LEVER_COMPANY_SLUGS` is empty.

### 1.7 Adzuna (`adzuna`)
- **Adapter Class**: `opportunity_radar.sources.adzuna.client.AdzunaSource`
- **Mechanism**: Official developer API integration supporting regional indices:
  ```http
  GET https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id={app_id}&app_key={app_key}&what={query}
  ```
- **Configuration**:
  - Requires `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`.
- **Parsing**: Ingests structured JSON results including salary ranges (`salary_min`, `salary_max`), exact company names, locations, and ISO 8601 creation dates.
- **Data Guarantees**:
  - Zero scraping; official API SLA.
  - Status reports `not_configured` when API keys are absent.

---

## 2. Source Diagnostics & Status Matrix

Opportunity Radar enforces **honest reporting** across all sources. Adapters return standardized `SourceRunResult` instances reflecting one of five operational states:

| Status (`SourceStatus`) | Description | Behavior |
| :--- | :--- | :--- |
| `success` | Source is configured, enabled, reachable, and returned valid listings. | Listings added to candidate radar pool. |
| `partial` | Source completed partially (e.g., rate-limited on page 2 or some queries timed out). | Available listings are preserved; diagnostic warning logged. |
| `not_configured` | Source is enabled but lacks necessary credentials or board slugs. | Request is bypassed gracefully without attempting invalid HTTP calls. |
| `disabled` | Source is explicitly turned off in settings (`ENABLE_*_SOURCE=false`). | Skipped during query dispatch. |
| `failed` | Source suffered unhandled network errors, HTTP 5xx errors, or parsing failures. | Logged in `SourceRunLogModel`; other sources continue without interruption. |

---

## 3. Configuration Matrix

| Source | Setting Flag | Required Credentials / Variables | Default |
| :--- | :--- | :--- | :--- |
| **Demo** | `DEMO_MODE=true` | `data/demo_jobs.json` file | `true` |
| **LinkedIn** | `ENABLE_LINKEDIN_SOURCE=true` | None (Public Guest Endpoint) | `true` |
| **WUZZUF** | `ENABLE_WUZZUF_SOURCE=true` | None (Public Search Listing) | `true` |
| **Remote OK** | `ENABLE_REMOTEOK_SOURCE=true` | None (Public JSON API) | `true` |
| **Greenhouse** | `ENABLE_GREENHOUSE_SOURCE=true` | `GREENHOUSE_BOARD_SLUGS=slug1,slug2` | `false` |
| **Lever** | `ENABLE_LEVER_SOURCE=true` | `LEVER_COMPANY_SLUGS=slug1,slug2` | `false` |
| **Adzuna** | `ENABLE_ADZUNA_SOURCE=true` | `ADZUNA_APP_ID=...`, `ADZUNA_APP_KEY=...` | `false` |
