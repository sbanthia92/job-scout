from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import structlog
from anthropic import AsyncAnthropic
from anthropic.types import TextBlock
from jinja2 import Template
from pydantic import ValidationError

from job_scout.models import Job, Profile, ScoredJob

log = structlog.get_logger()

SCORE_MODEL = "claude-haiku-4-5-20251001"
_PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "job_score.txt"

_SYSTEM_NORMAL = (
    "You are a job-market analyst. Score candidate–job fit and return only valid JSON."
)
_SYSTEM_STRICT = (
    "You are a job-market analyst. You MUST return ONLY a valid JSON object. "
    "No code blocks, no prose, no explanation — just the raw JSON object starting with {."
)


def _render_prompt(job: Job, profile: Profile) -> str:
    template = Template(_PROMPT_FILE.read_text())
    return template.render(
        job=job,
        target_titles=profile.target_titles,
        seniority=profile.seniority,
        target_locations=profile.target_locations,
        salary_floor=profile.salary_floor,
        ideal_role_description=profile.ideal_role_description,
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return cast(dict[str, Any], json.loads(match.group(1)))
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return cast(dict[str, Any], json.loads(match.group(0)))
    raise ValueError(f"No JSON object found in response: {text[:200]!r}")


async def _call_model(
    client: AsyncAnthropic,
    system: str,
    prompt: str,
) -> tuple[dict[str, Any], int, int]:
    response = await client.messages.create(
        model=SCORE_MODEL,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = ""
    for block in response.content:
        if isinstance(block, TextBlock):
            text = block.text
            break
    if not text:
        raise ValueError("LLM returned no text content")
    data = _extract_json(text)
    return data, response.usage.input_tokens, response.usage.output_tokens


async def score_job(
    job: Job,
    profile: Profile,
    client: AsyncAnthropic,
    alert_threshold: int = 90,
) -> ScoredJob | None:
    prompt = _render_prompt(job, profile)

    for attempt, system in enumerate([_SYSTEM_NORMAL, _SYSTEM_STRICT]):
        try:
            data, input_tokens, output_tokens = await _call_model(client, system, prompt)
            score = max(0, min(100, int(data["score"])))
            scored = ScoredJob(
                job=job,
                score=score,
                reasons=list(data.get("reasons") or []),
                flags=list(data.get("flags") or []),
                is_alert=score >= alert_threshold,
            )
            log.debug(
                "job_scored",
                job_id=job.id,
                score=score,
                is_alert=scored.is_alert,
                attempt=attempt,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            return scored
        except (json.JSONDecodeError, ValidationError, KeyError, TypeError, ValueError) as exc:
            log.warning(
                "score_attempt_failed",
                job_id=job.id,
                attempt=attempt,
                error=str(exc),
            )

    log.error("score_dropped", job_id=job.id, title=job.title)
    return None
