from __future__ import annotations

import pytest
from pydantic import ValidationError

from job_scout.models import Job, Profile, ScoredJob


def _make_job(**kwargs: object) -> Job:
    defaults: dict[str, object] = {
        "id": "acme::software engineer::san francisco",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "description": "Build cool things.",
        "source": "serpapi_abc123",
    }
    defaults.update(kwargs)
    return Job.model_validate(defaults)


def _make_profile(**kwargs: object) -> Profile:
    defaults: dict[str, object] = {
        "target_titles": ["Software Engineer", "Backend Engineer"],
        "seniority": ["senior", "staff"],
        "target_locations": ["San Francisco, CA", "Remote"],
        "requires_visa_sponsorship": False,
        "deal_breakers": ["blockchain"],
        "ideal_role_description": "Python backend work at a product company.",
        "work_artifacts": ["https://github.com/user/repo"],
        "raw_resume_text": "Jane Doe, 5 years Python experience.",
    }
    defaults.update(kwargs)
    return Profile.model_validate(defaults)


def test_job_round_trip() -> None:
    job = _make_job(salary_min=100_000.0, salary_max=150_000.0, is_remote=True)
    assert Job.model_validate(job.model_dump()) == job


def test_profile_round_trip() -> None:
    profile = _make_profile(salary_floor=120_000.0, requires_visa_sponsorship=True)
    assert Profile.model_validate(profile.model_dump()) == profile


def test_scored_job_round_trip() -> None:
    job = _make_job()
    scored = ScoredJob(
        job=job,
        score=85,
        reasons=["Great fit for Python backend role"],
        flags=[],
        is_alert=False,
    )
    assert ScoredJob.model_validate(scored.model_dump()) == scored


def test_scored_job_score_too_high() -> None:
    with pytest.raises(ValidationError):
        ScoredJob(job=_make_job(), score=101, reasons=[], flags=[], is_alert=False)


def test_scored_job_score_too_low() -> None:
    with pytest.raises(ValidationError):
        ScoredJob(job=_make_job(), score=-1, reasons=[], flags=[], is_alert=False)


def test_scored_job_score_boundary_values() -> None:
    job = _make_job()
    low = ScoredJob(job=job, score=0, reasons=[], flags=[], is_alert=False)
    high = ScoredJob(job=job, score=100, reasons=[], flags=[], is_alert=True)
    assert low.score == 0
    assert high.score == 100


def test_job_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        Job.model_validate({"title": "Engineer", "company": "Acme"})


def test_profile_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"target_titles": ["SWE"]})


def test_job_optional_salary_defaults_none() -> None:
    job = _make_job()
    assert job.salary_min is None
    assert job.salary_max is None
    assert job.salary_currency is None
    assert job.posted_at is None
    assert job.apply_link is None


def test_job_is_remote_defaults_false() -> None:
    assert _make_job().is_remote is False


def test_profile_salary_floor_optional() -> None:
    profile = _make_profile()
    assert profile.salary_floor is None


def test_job_with_all_optional_fields() -> None:
    job = _make_job(
        salary_min=80_000.0,
        salary_max=120_000.0,
        salary_currency="USD",
        is_remote=True,
        posted_at="2024-01-15",
        apply_link="https://example.com/apply",
    )
    assert job.salary_currency == "USD"
    assert job.is_remote is True
    assert job.posted_at == "2024-01-15"
