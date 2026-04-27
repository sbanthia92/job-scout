from __future__ import annotations

from pydantic import BaseModel, Field


class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    is_remote: bool = False
    posted_at: str | None = None
    apply_link: str | None = None
    source: str


class Profile(BaseModel):
    target_titles: list[str]
    seniority: list[str]
    target_locations: list[str]
    salary_floor: float | None = None
    requires_visa_sponsorship: bool
    deal_breakers: list[str]
    ideal_role_description: str
    work_artifacts: list[str]
    raw_resume_text: str


class ScoredJob(BaseModel):
    job: Job
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    flags: list[str]
    is_alert: bool
