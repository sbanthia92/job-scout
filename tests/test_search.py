from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from job_scout.search import search_jobs

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "serpapi"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text())  # type: ignore[no-any-return]


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient()


# ---------------------------------------------------------------------------
# Standard listing
# ---------------------------------------------------------------------------

async def test_search_standard_listing() -> None:
    fixture = load_fixture("standard_listing.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(return_value=httpx.Response(200, json=fixture))
        async with _client() as client:
            jobs = await search_jobs(
                query="software engineer",
                location="San Francisco, CA",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Software Engineer"
    assert job.company == "Acme Corp"
    assert job.location == "San Francisco, CA"
    assert job.salary_min == 150_000
    assert job.salary_max == 180_000
    assert job.salary_currency == "USD"
    assert job.is_remote is False
    assert job.posted_at == "3 days ago"
    assert job.apply_link == "https://acme.com/jobs/123"
    assert job.source == "serpapi_abc123"


# ---------------------------------------------------------------------------
# No salary
# ---------------------------------------------------------------------------

async def test_search_no_salary() -> None:
    fixture = load_fixture("no_salary.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(return_value=httpx.Response(200, json=fixture))
        async with _client() as client:
            jobs = await search_jobs(
                query="backend engineer",
                location="New York, NY",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.salary_min is None
    assert job.salary_max is None
    assert job.salary_currency is None
    assert job.apply_link is None


# ---------------------------------------------------------------------------
# Explicit no-sponsorship — job parses successfully (filtering is filters.py's job)
# ---------------------------------------------------------------------------

async def test_search_no_sponsorship_listing_parses() -> None:
    fixture = load_fixture("no_sponsorship.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(return_value=httpx.Response(200, json=fixture))
        async with _client() as client:
            jobs = await search_jobs(
                query="software engineer",
                location="Chicago, IL",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 1
    assert "visa sponsorship" in jobs[0].description.lower()


# ---------------------------------------------------------------------------
# Remote listing — is_remote flag
# ---------------------------------------------------------------------------

async def test_search_remote_listing() -> None:
    fixture = load_fixture("remote_listing.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(return_value=httpx.Response(200, json=fixture))
        async with _client() as client:
            jobs = await search_jobs(
                query="staff engineer",
                location="Remote",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 1
    assert jobs[0].is_remote is True


# ---------------------------------------------------------------------------
# Deal-breaker keyword in title — job still parses (filtering is filters.py's job)
# ---------------------------------------------------------------------------

async def test_search_deal_breaker_title_parses() -> None:
    fixture = load_fixture("deal_breaker_title.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(return_value=httpx.Response(200, json=fixture))
        async with _client() as client:
            jobs = await search_jobs(
                query="software engineer",
                location="San Francisco, CA",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 1
    assert "blockchain" in jobs[0].title.lower()


# ---------------------------------------------------------------------------
# Pagination — collects results from both pages
# ---------------------------------------------------------------------------

async def test_search_pagination() -> None:
    page1 = load_fixture("paginated_page1.json")
    page2 = load_fixture("paginated_page2.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(
            side_effect=[
                httpx.Response(200, json=page1),
                httpx.Response(200, json=page2),
            ]
        )
        async with _client() as client:
            jobs = await search_jobs(
                query="engineer",
                location="Remote",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 2
    titles = {j.title for j in jobs}
    assert "Python Engineer" in titles
    assert "Go Engineer" in titles


# ---------------------------------------------------------------------------
# 5xx retry — succeeds on second attempt
# ---------------------------------------------------------------------------

async def test_search_5xx_retries_and_succeeds() -> None:
    fixture = load_fixture("standard_listing.json")
    with (
        respx.mock,
        patch("job_scout.search.asyncio.sleep", new_callable=AsyncMock),
    ):
        respx.get(SERPAPI_BASE_URL).mock(
            side_effect=[
                httpx.Response(500, json={"error": "Server Error"}),
                httpx.Response(200, json=fixture),
            ]
        )
        async with _client() as client:
            jobs = await search_jobs(
                query="software engineer",
                location="San Francisco, CA",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert len(jobs) == 1


# ---------------------------------------------------------------------------
# 5xx on both attempts — raises HTTPStatusError
# ---------------------------------------------------------------------------

async def test_search_5xx_both_attempts_raises() -> None:
    with (
        respx.mock,
        patch("job_scout.search.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(httpx.HTTPStatusError),
    ):
        respx.get(SERPAPI_BASE_URL).mock(
            return_value=httpx.Response(500, json={"error": "Server Error"})
        )
        async with _client() as client:
            await search_jobs(
                query="software engineer",
                location="San Francisco, CA",
                date_posted="week",
                api_key="test_key",
                client=client,
            )


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------

async def test_search_empty_results() -> None:
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(
            return_value=httpx.Response(200, json={"jobs_results": []})
        )
        async with _client() as client:
            jobs = await search_jobs(
                query="very obscure query xyz",
                location="Remote",
                date_posted="today",
                api_key="test_key",
                client=client,
            )

    assert jobs == []


# ---------------------------------------------------------------------------
# Job ID construction
# ---------------------------------------------------------------------------

async def test_search_job_id_format() -> None:
    fixture = load_fixture("standard_listing.json")
    with respx.mock:
        respx.get(SERPAPI_BASE_URL).mock(return_value=httpx.Response(200, json=fixture))
        async with _client() as client:
            jobs = await search_jobs(
                query="software engineer",
                location="San Francisco, CA",
                date_posted="week",
                api_key="test_key",
                client=client,
            )

    assert jobs[0].id == "acme corp::senior software engineer::san francisco, ca"


# Import the constant so we don't hardcode the URL in every test
from job_scout.search import SERPAPI_BASE_URL  # noqa: E402
