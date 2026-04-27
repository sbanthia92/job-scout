# Job-Scout — CLAUDE.md

Source of truth for architecture, tech stack, conventions, and behavioral rules.

## Project overview

A Python CLI + GitHub Actions cron that pulls jobs from SerpApi's Google Jobs API
every 6 hours, scores them against my profile using Claude Haiku 4.5, and emails
matches via Resend. State lives in a private GitHub Gist. No database.

## Tech stack

- **Language:** Python 3.12+
- **CLI framework:** Typer
- **HTTP client:** httpx (async)
- **Data models:** Pydantic v2 (strict, no Optional unless genuinely optional)
- **AI:** Anthropic SDK — Sonnet 4.5 for resume parsing, Haiku 4.5 for scoring
- **PDF parsing:** pdfplumber (primary), pypdf (fallback)
- **Templating:** Jinja2
- **Logging:** structlog
- **Encryption:** cryptography (Fernet)
- **Config:** PyYAML
- **Email:** Resend
- **State:** Private GitHub Gist
- **Linting/formatting:** ruff
- **Type checking:** mypy --strict
- **Testing:** pytest + pytest-asyncio + respx (httpx mocking)

## Repo layout

```
Job-Scout/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── claude-pr-review.yml
│       ├── claude-ci-fix.yml
│       └── claude-interactive.yml
├── .pre-commit-config.yaml
├── .gitignore
├── CLAUDE.md
├── README.md
├── config.example.yaml
├── pyproject.toml
├── prompts/
│   ├── resume_parse.txt
│   └── job_score.txt
├── src/
│   └── job_scout/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── dedupe.py
│       ├── filters.py
│       ├── models.py
│       ├── profile.py
│       ├── score.py
│       └── search.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── fixtures/
    │   └── serpapi/
    ├── golden/
    ├── test_config.py
    ├── test_dedupe.py
    ├── test_filters.py
    ├── test_models.py
    ├── test_pipeline.py
    ├── test_profile.py
    ├── test_score.py
    └── test_search.py
```

## Pydantic models

### Job

Fields from SerpApi Google Jobs response:

```python
class Job(BaseModel):
    id: str                        # constructed: f"{company}::{title}::{location}" normalized
    title: str
    company: str
    location: str
    description: str
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    is_remote: bool = False
    posted_at: str | None = None   # ISO date string from SerpApi
    apply_link: str | None = None
    source: str                    # SerpApi job_id or detected_extensions source
```

### Profile

```python
class Profile(BaseModel):
    target_titles: list[str]
    seniority: list[str]           # e.g. ["senior", "staff", "principal"]
    target_locations: list[str]
    salary_floor: float | None = None
    requires_visa_sponsorship: bool
    deal_breakers: list[str]       # keywords that auto-reject
    ideal_role_description: str
    work_artifacts: list[str]      # URLs or descriptions
    raw_resume_text: str
```

### ScoredJob

```python
class ScoredJob(BaseModel):
    job: Job
    score: int                     # 0–100
    reasons: list[str]             # bullet points from LLM
    flags: list[str]               # deal-breaker hits, salary mismatch, etc.
    is_alert: bool                 # score >= alert_threshold
```

## Config schema (config.yaml)

```yaml
search:
  queries:
    - "software engineer"
    - "backend engineer"
  locations:
    - "San Francisco, CA"
    - "New York, NY"
    - "Remote"
  date_posted: "week"             # today | week | month

scoring:
  threshold: 70                   # minimum score to surface a job
  alert_threshold: 90             # score at which to flag for immediate attention

filters:
  deal_breakers:
    - "blockchain"
    - "crypto"
    - "gambling"

gist:
  id: ""                          # GitHub Gist ID for seen-jobs state
  filename: "seen_jobs.json"

email:
  from: "scout@example.com"
  to: "you@example.com"
```

## CLI commands

### `scout setup`

1. `--resume PATH` — path to resume PDF
2. Prompt for: target titles, seniority levels, target locations, salary floor,
   visa sponsorship required (y/n), deal-breaker keywords, ideal role description,
   work artifact links
3. Call Sonnet 4.5 with prompts/resume_parse.txt
4. Show parsed Profile for confirmation
5. Write profile.encrypted.json (Fernet, key from PROFILE_ENCRYPTION_KEY env var)

Prompt order matches the Profile field order above.

### `scout run [--dry-run]`

Pipeline:
1. Load and decrypt profile
2. Read seen-jobs from Gist (abort on read failure)
3. Fan out searches across all (query, location) combos
4. Deduplicate against seen-jobs
5. Apply hard filters (deal_breakers, visa, salary floor)
6. Score survivors with Haiku 4.5 concurrently (semaphore=5)
7. Filter by threshold
8. In dry-run: print formatted summary, do NOT email, do NOT update Gist
9. In live run: send email via Resend, update Gist

## Scoring prompt conventions

File: prompts/job_score.txt

- Version comment at top: `# version: 1`
- Returns strict JSON matching ScoredJob schema (minus the `job` field — score, reasons, flags, is_alert)
- One Anthropic call per job
- Retry once with stricter system message on validation failure
- Drop and log on second failure
- Log token counts (input, output, cache read, cache write)

## Resume parse prompt conventions

File: prompts/resume_parse.txt

- Uses Claude Sonnet 4.5
- Strict JSON schema in the prompt matching Profile (minus raw_resume_text)
- raw_resume_text is appended by profile.py, not by the LLM

## Hard filters (filters.py)

Each filter is a pure function `(Job, Profile) -> bool` returning True = keep.

- `filter_deal_breakers(job, profile)` — drops if any deal-breaker keyword appears in title (case-insensitive)
- `filter_visa(job, profile)` — drops only on explicit sponsorship-refusal patterns (e.g. "no sponsorship", "must be authorized", "no visa"). Silent jobs pass through.
- `filter_salary_floor(job, profile)` — drops only if salary_max is known AND salary_max < profile.salary_floor

## Deduplication (dedupe.py)

- `SeenJobsStore` — Protocol with `read() -> dict[str, str]` and `write(dict[str, str]) -> None`
- `GistSeenJobsStore` — real implementation, reads/writes a GitHub Gist via httpx
- `LocalFileSeenJobsStore` — dev/test implementation, reads/writes a local JSON file
- Job ID generation: `f"{job.company}::{job.title}::{job.location}".lower().strip()` — normalized. Fallback content hash if any field is empty.
- Prune entries older than 30 days on every write
- On Gist read failure: raise, abort the run
- On Gist write failure: log warning, continue (jobs already emailed)

## Structured logging

Use structlog throughout. Never use print() or the stdlib logging module directly.

End of every `scout run` with this exact log line:

```python
log.info(
    "run_summary",
    jobs_fetched=n,
    jobs_after_dedupe=n,
    jobs_after_filters=n,
    jobs_scored=n,
    jobs_surfaced=n,
    jobs_alerted=n,
    dry_run=bool,
)
```

## CI/PR pipeline (Checkpoint 8)

Three GitHub Actions workflows using `anthropics/claude-code-action@v1`:

### claude-pr-review.yml
- Triggers: PR open, push to PR branch
- Reads diff + full context of changed files
- Checks: logic errors, missing error handling, security issues, CLAUDE.md violations
- Posts inline PR comments with file:line references
- Tags: Important 🔴 or Nit 🟡; cap nits at 5, summarize remainder as count
- Skips: generated files, lockfiles, fixtures
- Max 5 turns

### claude-ci-fix.yml
- Triggers: CI check failure on PR
- Reads CI failure logs, investigates root cause, pushes fix commit
- If flaky/env issue: posts comment instead of pushing speculative fix
- Loop max 3 per PR, tracked via labels: ci-fix-attempt-1/2/3
- After 3 failures: post comment for human review, stop

### claude-interactive.yml
- Triggers: @claude mentions in PR comments or issues
- Responds to ad-hoc requests

### Permissions (all three workflows)
```yaml
permissions:
  contents: write
  pull-requests: write
  issues: read
  checks: read
```

### Separation of concerns
- Review workflow flags issues, does NOT auto-fix
- Auto-fix is reserved for CI failures only
- Human checkpoint is preserved for review-flagged issues

## Branch protection (main)

- claude-pr-review check must pass
- ci.yml (ruff + mypy + pytest) must pass
- At least 1 approving review (Claude's review counts via GitHub App)
- Auto-merge: squash strategy

## Commit conventions

- Conventional Commits: `feat:`, `fix:`, `test:`, `chore:`, `docs:`, `refactor:`
- One commit per checkpoint on a feature branch, not on main
- Never commit to main directly

## Behavioral rules

- Follow this file strictly. Ask before deviating.
- No real network calls in tests. Ever.
- Type hints on every public function.
- mypy --strict must pass.
- Pydantic models, not dicts, across module boundaries.
- structlog, not print().
- Do not add features not in this file or the session prompt without asking.
