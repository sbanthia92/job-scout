from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

import pdfplumber
import structlog
from anthropic import Anthropic
from anthropic.types import TextBlock
from cryptography.fernet import Fernet
from jinja2 import Template
from pypdf import PdfReader

from job_scout.models import Profile

log = structlog.get_logger()

RESUME_PARSE_MODEL = "claude-sonnet-4-5-20251001"
_PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "resume_parse.txt"


def extract_text_from_pdf(path: Path) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(pages).strip()
        if text:
            log.debug("pdf_extracted", method="pdfplumber", chars=len(text))
            return text
    except Exception as exc:
        log.warning("pdfplumber_failed", path=str(path), error=str(exc))

    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    log.debug("pdf_extracted", method="pypdf", chars=len(text))
    return text


def _render_prompt(
    raw_text: str,
    target_titles: list[str],
    seniority: list[str],
    target_locations: list[str],
    salary_floor: float | None,
    requires_visa_sponsorship: bool,
    deal_breakers: list[str],
    ideal_role_description: str,
    work_artifacts: list[str],
) -> str:
    template = Template(_PROMPT_FILE.read_text())
    return template.render(
        raw_resume_text=raw_text,
        target_titles=target_titles,
        seniority=seniority,
        target_locations=target_locations,
        salary_floor=salary_floor,
        requires_visa_sponsorship=requires_visa_sponsorship,
        deal_breakers=deal_breakers,
        ideal_role_description=ideal_role_description,
        work_artifacts=work_artifacts,
    )


def _create_message(client: Anthropic, prompt: str) -> str:
    response = client.messages.create(
        model=RESUME_PARSE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    log.debug(
        "llm_tokens",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    for block in response.content:
        if isinstance(block, TextBlock):
            return block.text
    raise ValueError("LLM returned no text content")


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return cast(dict[str, Any], json.loads(match.group(1)))
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return cast(dict[str, Any], json.loads(match.group(0)))
    raise ValueError(f"No JSON found in LLM response: {text[:200]!r}")


def parse_resume(
    *,
    raw_text: str,
    target_titles: list[str],
    seniority: list[str],
    target_locations: list[str],
    salary_floor: float | None,
    requires_visa_sponsorship: bool,
    deal_breakers: list[str],
    ideal_role_description: str,
    work_artifacts: list[str],
    client: Anthropic,
) -> Profile:
    prompt = _render_prompt(
        raw_text=raw_text,
        target_titles=target_titles,
        seniority=seniority,
        target_locations=target_locations,
        salary_floor=salary_floor,
        requires_visa_sponsorship=requires_visa_sponsorship,
        deal_breakers=deal_breakers,
        ideal_role_description=ideal_role_description,
        work_artifacts=work_artifacts,
    )
    content = _create_message(client, prompt)
    data = _extract_json(content)
    data["raw_resume_text"] = raw_text
    return Profile.model_validate(data)


def encrypt_profile(profile: Profile, key: bytes) -> bytes:
    return Fernet(key).encrypt(profile.model_dump_json().encode())


def decrypt_profile(data: bytes, key: bytes) -> Profile:
    return Profile.model_validate_json(Fernet(key).decrypt(data))


def save_profile(profile: Profile, path: Path, key: bytes) -> None:
    path.write_bytes(encrypt_profile(profile, key))
    log.info("profile_saved", path=str(path))


def load_profile(path: Path, key: bytes) -> Profile:
    return decrypt_profile(path.read_bytes(), key)
