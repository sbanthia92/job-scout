from __future__ import annotations

import asyncio
import hashlib
from typing import Any, cast

import httpx
import structlog

from job_scout.models import Job

log = structlog.get_logger()

SERPAPI_BASE_URL = "https://serpapi.com/search.json"
MAX_PAGES = 3
_TIMEOUT = httpx.Timeout(30.0)


def _make_job_id(company: str, title: str, location: str) -> str:
    key = f"{company}::{title}::{location}".lower().strip()
    if not (company and title and location):
        return hashlib.md5(key.encode()).hexdigest()
    return key


def _parse_salary(
    result: dict[str, Any],
) -> tuple[float | None, float | None, str | None]:
    salaries = result.get("salaries") or []
    if salaries and isinstance(salaries, list):
        first = salaries[0]
        return first.get("min_salary"), first.get("max_salary"), first.get("currency")
    return None, None, None


def _parse_job(result: dict[str, Any]) -> Job | None:
    try:
        title: str = result.get("title") or ""
        company: str = result.get("company_name") or ""
        location: str = result.get("location") or ""
        description: str = result.get("description") or ""
        job_id: str = result.get("job_id") or ""

        if not (title and company and description):
            log.debug("job_skipped_missing_fields", title=title, company=company)
            return None

        extensions: dict[str, Any] = result.get("detected_extensions") or {}
        is_remote = bool(extensions.get("work_from_home", False)) or "remote" in location.lower()

        posted_at_raw = extensions.get("posted_at")
        posted_at = str(posted_at_raw) if posted_at_raw is not None else None

        apply_options: list[Any] = result.get("apply_options") or []
        apply_link: str | None = apply_options[0].get("link") if apply_options else None

        salary_min, salary_max, salary_currency = _parse_salary(result)

        return Job(
            id=_make_job_id(company, title, location),
            title=title,
            company=company,
            location=location,
            description=description,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            is_remote=is_remote,
            posted_at=posted_at,
            apply_link=apply_link,
            source=job_id,
        )
    except Exception as exc:
        log.warning("job_parse_failed", error=str(exc))
        return None


async def _get_page(
    client: httpx.AsyncClient,
    params: dict[str, str],
) -> dict[str, Any]:
    response = await client.get(SERPAPI_BASE_URL, params=params, timeout=_TIMEOUT)
    if response.status_code >= 500:
        log.warning("serpapi_5xx_retry", status=response.status_code)
        await asyncio.sleep(1.0)
        response = await client.get(SERPAPI_BASE_URL, params=params, timeout=_TIMEOUT)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


async def search_jobs(
    *,
    query: str,
    location: str,
    date_posted: str,
    api_key: str,
    client: httpx.AsyncClient,
) -> list[Job]:
    params: dict[str, str] = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "date_posted": date_posted,
        "api_key": api_key,
    }

    jobs: list[Job] = []
    for page in range(MAX_PAGES):
        data = await _get_page(client, params)
        results: list[Any] = data.get("jobs_results") or []

        for result in results:
            job = _parse_job(result)
            if job is not None:
                jobs.append(job)

        log.debug("serpapi_page", page=page, results=len(results), cumulative=len(jobs))

        pagination: dict[str, Any] = data.get("serpapi_pagination") or {}
        next_token: str | None = pagination.get("next_page_token")
        if not next_token:
            break
        params["next_page_token"] = next_token

    log.info("search_complete", query=query, location=location, jobs=len(jobs))
    return jobs
