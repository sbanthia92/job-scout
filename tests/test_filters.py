from __future__ import annotations

from job_scout.filters import apply_filters, filter_deal_breakers, filter_salary_floor, filter_visa
from job_scout.models import Job, Profile


def _make_job(**kwargs: object) -> Job:
    defaults: dict[str, object] = {
        "id": "acme::software engineer::sf",
        "title": "Software Engineer",
        "company": "Acme",
        "location": "San Francisco, CA",
        "description": "Join our team building great software products.",
        "source": "serpapi_abc",
    }
    defaults.update(kwargs)
    return Job.model_validate(defaults)


def _make_profile(**kwargs: object) -> Profile:
    defaults: dict[str, object] = {
        "target_titles": ["Software Engineer"],
        "seniority": ["senior"],
        "target_locations": ["San Francisco, CA"],
        "requires_visa_sponsorship": False,
        "deal_breakers": ["blockchain", "crypto"],
        "ideal_role_description": "Python backend work.",
        "work_artifacts": [],
        "raw_resume_text": "Resume text.",
    }
    defaults.update(kwargs)
    return Profile.model_validate(defaults)


# ---------------------------------------------------------------------------
# filter_deal_breakers
# ---------------------------------------------------------------------------

def test_deal_breaker_in_title_drops() -> None:
    job = _make_job(title="Blockchain Software Engineer")
    assert filter_deal_breakers(job, _make_profile()) is False


def test_deal_breaker_case_insensitive() -> None:
    job = _make_job(title="CRYPTO ENGINEER")
    assert filter_deal_breakers(job, _make_profile()) is False


def test_deal_breaker_partial_word_in_title_drops() -> None:
    job = _make_job(title="Senior Crypto Analyst")
    assert filter_deal_breakers(job, _make_profile()) is False


def test_no_deal_breaker_in_title_passes() -> None:
    job = _make_job(title="Senior Software Engineer")
    assert filter_deal_breakers(job, _make_profile()) is True


def test_deal_breaker_only_in_description_not_filtered() -> None:
    job = _make_job(
        title="Software Engineer",
        description="Blockchain experience is a nice-to-have.",
    )
    assert filter_deal_breakers(job, _make_profile()) is True


def test_empty_deal_breakers_list_passes_all() -> None:
    profile = _make_profile(deal_breakers=[])
    job = _make_job(title="Blockchain Engineer")
    assert filter_deal_breakers(job, profile) is True


# ---------------------------------------------------------------------------
# filter_visa
# ---------------------------------------------------------------------------

def test_visa_not_required_always_passes() -> None:
    profile = _make_profile(requires_visa_sponsorship=False)
    job = _make_job(description="No visa sponsorship available.")
    assert filter_visa(job, profile) is True


def test_visa_required_explicit_no_sponsorship_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="We do not offer visa sponsorship for this role.")
    assert filter_visa(job, profile) is False


def test_visa_required_must_be_authorized_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="Candidates must be legally authorized to work in the US.")
    assert filter_visa(job, profile) is False


def test_visa_required_no_sponsorship_short_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="Great role. No sponsorship. Apply now.")
    assert filter_visa(job, profile) is False


def test_visa_required_no_h1b_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="No H1B visa sponsorship for this position.")
    assert filter_visa(job, profile) is False


def test_visa_required_no_visa_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="No visa transfer. Must already hold authorization.")
    assert filter_visa(job, profile) is False


def test_visa_required_silent_job_passes() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="Join our engineering team. Competitive salary.")
    assert filter_visa(job, profile) is True


def test_visa_required_sponsorship_offered_passes() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="We offer visa sponsorship for qualified candidates.")
    assert filter_visa(job, profile) is True


# ---------------------------------------------------------------------------
# filter_salary_floor
# ---------------------------------------------------------------------------

def test_salary_floor_none_always_passes() -> None:
    profile = _make_profile(salary_floor=None)
    job = _make_job(salary_max=50_000.0)
    assert filter_salary_floor(job, profile) is True


def test_salary_max_unknown_always_passes() -> None:
    profile = _make_profile(salary_floor=150_000.0)
    job = _make_job()  # salary_max defaults to None
    assert filter_salary_floor(job, profile) is True


def test_salary_max_below_floor_drops() -> None:
    profile = _make_profile(salary_floor=150_000.0)
    job = _make_job(salary_max=120_000.0)
    assert filter_salary_floor(job, profile) is False


def test_salary_max_equals_floor_passes() -> None:
    profile = _make_profile(salary_floor=150_000.0)
    job = _make_job(salary_max=150_000.0)
    assert filter_salary_floor(job, profile) is True


def test_salary_max_above_floor_passes() -> None:
    profile = _make_profile(salary_floor=150_000.0)
    job = _make_job(salary_max=200_000.0)
    assert filter_salary_floor(job, profile) is True


# ---------------------------------------------------------------------------
# apply_filters — composite
# ---------------------------------------------------------------------------

def test_apply_filters_passes_clean_job() -> None:
    profile = _make_profile(
        requires_visa_sponsorship=True,
        salary_floor=100_000.0,
    )
    job = _make_job(
        title="Senior Software Engineer",
        description="Great Python role. Visa sponsorship available.",
        salary_max=150_000.0,
    )
    assert apply_filters(job, profile) is True


def test_apply_filters_drops_on_deal_breaker() -> None:
    profile = _make_profile()
    job = _make_job(title="Crypto Engineer")
    assert apply_filters(job, profile) is False


def test_apply_filters_drops_on_visa_refusal() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="No sponsorship provided. Must be authorized.")
    assert apply_filters(job, profile) is False


def test_apply_filters_drops_on_low_salary() -> None:
    profile = _make_profile(salary_floor=150_000.0)
    job = _make_job(salary_max=90_000.0)
    assert apply_filters(job, profile) is False
