from __future__ import annotations

from job_scout.filters import (
    apply_non_negotiable_filters,
    filter_deal_breakers,
    filter_location,
    filter_visa,
    flag_salary_mismatch,
)
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
        "target_locations": ["San Francisco, CA", "Remote"],
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


def test_visa_required_citizens_only_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="Open to US citizens only.")
    assert filter_visa(job, profile) is False


def test_visa_required_clearance_required_drops() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="Security clearance required for this position.")
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
# filter_location
# ---------------------------------------------------------------------------

def test_location_remote_job_always_passes() -> None:
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(location="Remote", is_remote=True)
    assert filter_location(job, profile) is True


def test_location_onsite_in_target_city_passes() -> None:
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(
        location="San Diego, CA",
        description="This is a full-time on-site role in San Diego.",
    )
    assert filter_location(job, profile) is True


def test_location_onsite_outside_target_drops() -> None:
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(
        location="Austin, TX",
        description="This role is on-site in our Austin office.",
    )
    assert filter_location(job, profile) is False


def test_location_hybrid_outside_target_drops() -> None:
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(
        location="Seattle, WA",
        description="Hybrid role — 3 days per week in Seattle office.",
    )
    assert filter_location(job, profile) is False


def test_location_silent_listing_passes() -> None:
    """Job with no on-site/hybrid signal passes through regardless of location."""
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(
        location="Chicago, IL",
        description="Join our growing team. Competitive salary and benefits.",
    )
    assert filter_location(job, profile) is True


def test_location_hybrid_in_target_city_passes() -> None:
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(
        location="San Diego, CA",
        description="Hybrid schedule — 2 days on-site in San Diego.",
    )
    assert filter_location(job, profile) is True


# ---------------------------------------------------------------------------
# flag_salary_mismatch — soft negotiable signal
# ---------------------------------------------------------------------------

def test_flag_salary_no_floor_returns_none() -> None:
    profile = _make_profile(salary_floor=None)
    job = _make_job(salary_max=50_000.0)
    assert flag_salary_mismatch(job, profile) is None


def test_flag_salary_unknown_max_returns_none() -> None:
    profile = _make_profile(salary_floor=200_000.0)
    job = _make_job()  # salary_max defaults to None
    assert flag_salary_mismatch(job, profile) is None


def test_flag_salary_below_floor_returns_flag() -> None:
    profile = _make_profile(salary_floor=200_000.0)
    job = _make_job(salary_max=175_000.0)
    flag = flag_salary_mismatch(job, profile)
    assert flag is not None
    assert "175,000" in flag
    assert "200,000" in flag


def test_flag_salary_at_floor_returns_none() -> None:
    profile = _make_profile(salary_floor=200_000.0)
    job = _make_job(salary_max=200_000.0)
    assert flag_salary_mismatch(job, profile) is None


def test_flag_salary_above_floor_returns_none() -> None:
    profile = _make_profile(salary_floor=200_000.0)
    job = _make_job(salary_max=260_000.0)
    assert flag_salary_mismatch(job, profile) is None


# ---------------------------------------------------------------------------
# apply_non_negotiable_filters — composite
# ---------------------------------------------------------------------------

def test_apply_filters_passes_clean_job() -> None:
    profile = _make_profile(
        requires_visa_sponsorship=True,
        target_locations=["San Diego, CA", "Remote"],
    )
    job = _make_job(
        title="Senior Software Engineer",
        location="Remote",
        is_remote=True,
        description="Great Python role. Visa sponsorship available.",
        salary_max=150_000.0,
    )
    assert apply_non_negotiable_filters(job, profile) is True


def test_apply_filters_drops_on_deal_breaker() -> None:
    profile = _make_profile()
    job = _make_job(title="Crypto Engineer")
    assert apply_non_negotiable_filters(job, profile) is False


def test_apply_filters_drops_on_visa_refusal() -> None:
    profile = _make_profile(requires_visa_sponsorship=True)
    job = _make_job(description="No sponsorship provided. Must be authorized.")
    assert apply_non_negotiable_filters(job, profile) is False


def test_apply_filters_drops_on_onsite_outside_target() -> None:
    profile = _make_profile(target_locations=["San Diego, CA", "Remote"])
    job = _make_job(
        location="New York, NY",
        description="On-site role at our New York headquarters.",
    )
    assert apply_non_negotiable_filters(job, profile) is False


def test_apply_filters_low_salary_passes_through() -> None:
    """Salary below floor no longer causes a hard drop — it's a soft signal."""
    profile = _make_profile(salary_floor=200_000.0)
    job = _make_job(salary_max=90_000.0)
    assert apply_non_negotiable_filters(job, profile) is True
