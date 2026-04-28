from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from job_scout.models import Job, Profile, ScoredJob
from job_scout.score import _extract_json, score_job

GOLDEN_DIR = Path(__file__).parent / "golden"

GOLDEN_PROFILE = Profile.model_validate(
    {
        "target_titles": [
            "Senior Software Engineer",
            "Staff Software Engineer",
            "Senior Backend Engineer",
            "Staff Backend Engineer",
        ],
        "seniority": ["senior", "staff"],
        "target_locations": ["San Diego, CA", "Remote"],
        "salary_floor": 200_000.0,
        "requires_visa_sponsorship": True,
        "deal_breakers": ["clearance", "blockchain", "crypto"],
        "ideal_role_description": (
            "Python backend engineer at a product company, building distributed systems "
            "and APIs. Strong DevOps skills but prefer SWE-first roles over pure ops."
        ),
        "work_artifacts": [],
        "raw_resume_text": "5 years of Python backend experience building distributed systems.",
    }
)


def _make_job(**kwargs: object) -> Job:
    defaults: dict[str, object] = {
        "id": "acme::senior software engineer::san francisco",
        "title": "Senior Software Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "description": "Python backend role building distributed systems.",
        "source": "serpapi_abc",
    }
    defaults.update(kwargs)
    return Job.model_validate(defaults)


def _make_profile(**kwargs: object) -> Profile:
    defaults: dict[str, object] = {
        "target_titles": ["Senior Software Engineer", "Backend Engineer"],
        "seniority": ["senior", "staff"],
        "target_locations": ["San Francisco, CA", "Remote"],
        "salary_floor": 150_000.0,
        "requires_visa_sponsorship": False,
        "deal_breakers": ["blockchain"],
        "ideal_role_description": "Python backend at a product company.",
        "work_artifacts": [],
        "raw_resume_text": "5 years Python experience.",
    }
    defaults.update(kwargs)
    return Profile.model_validate(defaults)


def _mock_call_result(score: int, reasons: list[str] | None = None, flags: list[str] | None = None) -> tuple[dict[str, Any], int, int]:
    return (
        {
            "score": score,
            "reasons": reasons or ["Good title match", "Salary in range"],
            "flags": flags or [],
            "is_alert": score >= 90,
        },
        100,
        80,
    )


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

def test_extract_json_raw_object() -> None:
    text = '{"score": 85, "reasons": ["good"], "flags": [], "is_alert": false}'
    data = _extract_json(text)
    assert data["score"] == 85


def test_extract_json_code_block() -> None:
    text = '```json\n{"score": 72, "reasons": ["ok"], "flags": [], "is_alert": false}\n```'
    data = _extract_json(text)
    assert data["score"] == 72


def test_extract_json_no_json_raises() -> None:
    with pytest.raises(ValueError, match="No JSON"):
        _extract_json("Sorry, I cannot score this job.")


# ---------------------------------------------------------------------------
# score_job — happy path
# ---------------------------------------------------------------------------

async def test_score_job_returns_scored_job() -> None:
    job = _make_job()
    profile = _make_profile()
    mock_client = MagicMock(spec_set=["messages"])

    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = _mock_call_result(score=82)
        result = await score_job(job, profile, mock_client)
    assert isinstance(result, ScoredJob)
    assert result.score == 82
    assert result.is_alert is False
    assert result.job == job


async def test_score_job_is_alert_true_at_threshold() -> None:
    job = _make_job()
    profile = _make_profile()
    mock_client = MagicMock()

    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = _mock_call_result(score=90)
        result = await score_job(job, profile, mock_client, alert_threshold=90)
    assert result is not None
    assert result.is_alert is True


async def test_score_job_overrides_llm_is_alert() -> None:
    """is_alert is always computed from score, not trusted from LLM."""
    job = _make_job()
    profile = _make_profile()
    mock_client = MagicMock()

    # LLM says is_alert=True but score is 75 — we should override
    data: dict[str, Any] = {
        "score": 75,
        "reasons": ["ok"],
        "flags": [],
        "is_alert": True,  # LLM got it wrong
    }
    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = (data, 100, 80)
        result = await score_job(job, profile, mock_client, alert_threshold=90)
    assert result is not None
    assert result.score == 75
    assert result.is_alert is False  # overridden correctly


async def test_score_job_clamps_score_to_100() -> None:
    job = _make_job()
    mock_client = MagicMock()

    data: dict[str, Any] = {"score": 110, "reasons": [], "flags": [], "is_alert": True}
    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = (data, 100, 80)
        result = await score_job(job, _make_profile(), mock_client)
    assert result is not None
    assert result.score == 100


async def test_score_job_clamps_score_to_0() -> None:
    job = _make_job()
    mock_client = MagicMock()

    data: dict[str, Any] = {"score": -5, "reasons": [], "flags": [], "is_alert": False}
    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = (data, 100, 80)
        result = await score_job(job, _make_profile(), mock_client)
    assert result is not None
    assert result.score == 0


# ---------------------------------------------------------------------------
# score_job — retry on parse failure
# ---------------------------------------------------------------------------

async def test_score_job_retries_on_json_error() -> None:
    import json

    job = _make_job()
    mock_client = MagicMock()

    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [
            json.JSONDecodeError("Expecting value", "", 0),
            _mock_call_result(score=78),
        ]
        result = await score_job(job, _make_profile(), mock_client)
    assert result is not None
    assert result.score == 78
    assert mock_call.call_count == 2


async def test_score_job_drops_on_two_failures() -> None:
    import json

    job = _make_job()
    mock_client = MagicMock()

    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        result = await score_job(job, _make_profile(), mock_client)
    assert result is None
    assert mock_call.call_count == 2


async def test_score_job_retries_on_validation_error() -> None:
    job = _make_job()
    mock_client = MagicMock()

    # First attempt returns invalid score type that survives JSON parse but fails Pydantic
    bad_data: dict[str, Any] = {
        "score": "not_a_number",
        "reasons": [],
        "flags": [],
        "is_alert": False,
    }
    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [
            (bad_data, 100, 80),
            _mock_call_result(score=65),
        ]
        result = await score_job(job, _make_profile(), mock_client)
    assert result is not None
    assert result.score == 65


# ---------------------------------------------------------------------------
# Golden cases — realistic job fixtures scored against GOLDEN_PROFILE
# ---------------------------------------------------------------------------

def _golden_fixtures() -> list[tuple[str, dict[str, Any]]]:
    return [
        (p.stem, json.loads(p.read_text()))
        for p in sorted(GOLDEN_DIR.glob("*.json"))
    ]


@pytest.mark.parametrize(
    "label,fixture",
    [(label, fix) for label, fix in _golden_fixtures()],
    ids=[label for label, _ in _golden_fixtures()],
)
async def test_golden_score_in_expected_range(label: str, fixture: dict[str, Any]) -> None:
    job = Job.model_validate(fixture["job"])
    expected_min: int = fixture["expected_score_min"]
    expected_max: int = fixture["expected_score_max"]
    mock_client = MagicMock()

    midpoint = (expected_min + expected_max) // 2
    call_result: tuple[dict[str, Any], int, int] = (
        {
            "score": midpoint,
            "reasons": [f"Score {midpoint} for {label}"],
            "flags": [],
            "is_alert": midpoint >= 90,
        },
        200,
        100,
    )

    with patch("job_scout.score._call_model", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = call_result
        result = await score_job(job, GOLDEN_PROFILE, mock_client)
    assert result is not None, f"score_job returned None for {label}"
    assert expected_min <= result.score <= expected_max, (
        f"{label}: score {result.score} outside [{expected_min}, {expected_max}]"
    )
    assert isinstance(result.job, Job)
    assert result.job.id == job.id
