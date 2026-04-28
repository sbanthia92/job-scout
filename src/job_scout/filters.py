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
]


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


def filter_salary_floor(job: Job, profile: Profile) -> bool:
    """Return False (drop) only when salary_max is known AND below the floor.

    Unknown salary (salary_max is None) always passes through.
    """
    if profile.salary_floor is None or job.salary_max is None:
        return True
    return job.salary_max >= profile.salary_floor


def apply_filters(job: Job, profile: Profile) -> bool:
    """Apply all hard filters in sequence. Returns True if the job should be kept."""
    return (
        filter_deal_breakers(job, profile)
        and filter_visa(job, profile)
        and filter_salary_floor(job, profile)
    )
