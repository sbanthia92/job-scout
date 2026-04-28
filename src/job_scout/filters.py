from __future__ import annotations

import re

from job_scout.models import Job, Profile

# Conservative patterns: only explicit refusals to sponsor.
# Ambiguous or silent listings pass through.
_NO_SPONSORSHIP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"no\s+(?:visa\s+)?sponsorship", re.IGNORECASE),
    re.compile(r"not\s+offer(?:ing)?\s+(?:visa\s+)?sponsorship", re.IGNORECASE),
    re.compile(r"must\s+be\s+(?:legally\s+)?authorized", re.IGNORECASE),
    re.compile(r"not\s+(?:able\s+)?to\s+(?:provide\s+|offer\s+)?sponsor", re.IGNORECASE),
    re.compile(r"unable\s+to\s+(?:provide\s+|offer\s+)?sponsor", re.IGNORECASE),
    re.compile(r"no\s+h[-\s]?1[-\s]?b", re.IGNORECASE),
    re.compile(r"no\s+visa", re.IGNORECASE),
    re.compile(r"citizens?\s+only", re.IGNORECASE),
    re.compile(r"security\s+clearance\s+required", re.IGNORECASE),
    re.compile(r"must\s+hold\s+(?:an?\s+)?(?:active\s+)?(?:us\s+|u\.s\.\s+)?security\s+clearance", re.IGNORECASE),
]

_ONSITE_HYBRID_PATTERN = re.compile(
    r"\b(?:on[-\s]?site|on-?site|hybrid)\b", re.IGNORECASE
)


def filter_deal_breakers(job: Job, profile: Profile) -> bool:
    """Return False (drop) if any deal-breaker keyword appears in the job title."""
    title_lower = job.title.lower()
    return not any(kw.lower() in title_lower for kw in profile.deal_breakers)


def filter_visa(job: Job, profile: Profile) -> bool:
    """Return False (drop) when the job explicitly refuses sponsorship and the
    candidate requires it.

    Conservative: only drop on explicit negation patterns. Silent listings pass.
    """
    if not profile.requires_visa_sponsorship:
        return True
    text = f"{job.title} {job.description}"
    return not any(pattern.search(text) for pattern in _NO_SPONSORSHIP_PATTERNS)


def filter_location(job: Job, profile: Profile) -> bool:
    """Return False (drop) when the job is on-site or hybrid in a location not
    in the candidate's target_locations list.

    Remote jobs always pass. On-site/hybrid in a target location passes.
    Silent listings (no on-site/hybrid signal) pass through.
    """
    if job.is_remote:
        return True
    text = f"{job.title} {job.description}"
    if not _ONSITE_HYBRID_PATTERN.search(text):
        return True
    target_lower = {loc.lower() for loc in profile.target_locations}
    job_location_lower = job.location.lower()
    return any(target in job_location_lower or job_location_lower in target for target in target_lower)


def apply_non_negotiable_filters(job: Job, profile: Profile) -> bool:
    """Apply all non-negotiable hard filters. Returns True if the job should be kept."""
    return (
        filter_deal_breakers(job, profile)
        and filter_visa(job, profile)
        and filter_location(job, profile)
    )


def flag_salary_mismatch(job: Job, profile: Profile) -> str | None:
    """Return a flag string if salary_max is known and below the candidate's floor.

    Returns None if salary is unknown, floor is unset, or salary meets the floor.
    This is a soft negotiable signal for the scorer — not a hard drop.
    """
    if profile.salary_floor is None or job.salary_max is None:
        return None
    if job.salary_max < profile.salary_floor:
        return f"salary_max ${job.salary_max:,.0f} is below floor ${profile.salary_floor:,.0f}"
    return None
