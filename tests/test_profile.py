from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

from job_scout.models import Profile
from job_scout.profile import (
    _extract_json,
    decrypt_profile,
    encrypt_profile,
    extract_text_from_pdf,
    load_profile,
    parse_resume,
    save_profile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_LLM_JSON = """\
```json
{
  "target_titles": ["Software Engineer", "Backend Engineer"],
  "seniority": ["senior", "staff"],
  "target_locations": ["San Francisco, CA", "Remote"],
  "salary_floor": 150000.0,
  "requires_visa_sponsorship": false,
  "deal_breakers": ["blockchain"],
  "ideal_role_description": "Senior Python backend engineer at a product company.",
  "work_artifacts": ["https://github.com/user/repo"]
}
```"""

MOCK_LLM_JSON_RAW = """\
{
  "target_titles": ["Data Engineer"],
  "seniority": ["senior"],
  "target_locations": ["Remote"],
  "salary_floor": null,
  "requires_visa_sponsorship": true,
  "deal_breakers": [],
  "ideal_role_description": "Data pipeline work.",
  "work_artifacts": []
}"""


def _make_profile() -> Profile:
    return Profile(
        target_titles=["Software Engineer"],
        seniority=["senior"],
        target_locations=["Remote"],
        salary_floor=120_000.0,
        requires_visa_sponsorship=False,
        deal_breakers=["blockchain"],
        ideal_role_description="Python backend work.",
        work_artifacts=["https://github.com/user/repo"],
        raw_resume_text="Jane Doe, 5 years Python experience.",
    )


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def test_extract_text_pdfplumber_success(tmp_path: Path) -> None:
    dummy = tmp_path / "resume.pdf"
    dummy.write_bytes(b"")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Jane Doe\nSoftware Engineer"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    with patch("pdfplumber.open") as mock_open:
        mock_open.return_value.__enter__.return_value = mock_pdf
        mock_open.return_value.__exit__.return_value = False
        text = extract_text_from_pdf(dummy)

    assert text == "Jane Doe\nSoftware Engineer"


def test_extract_text_pdfplumber_empty_falls_back_to_pypdf(tmp_path: Path) -> None:
    dummy = tmp_path / "resume.pdf"
    dummy.write_bytes(b"")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = None  # pdfplumber extracts nothing
    mock_pdf_plumber = MagicMock()
    mock_pdf_plumber.pages = [mock_page]

    mock_pypdf_page = MagicMock()
    mock_pypdf_page.extract_text.return_value = "Fallback text from pypdf"
    mock_reader = MagicMock()
    mock_reader.pages = [mock_pypdf_page]

    with (
        patch("pdfplumber.open") as mock_open,
        patch("job_scout.profile.PdfReader", return_value=mock_reader),
    ):
        mock_open.return_value.__enter__.return_value = mock_pdf_plumber
        mock_open.return_value.__exit__.return_value = False
        text = extract_text_from_pdf(dummy)

    assert text == "Fallback text from pypdf"


def test_extract_text_pdfplumber_exception_falls_back_to_pypdf(tmp_path: Path) -> None:
    dummy = tmp_path / "resume.pdf"
    dummy.write_bytes(b"")

    mock_pypdf_page = MagicMock()
    mock_pypdf_page.extract_text.return_value = "Pypdf extracted text"
    mock_reader = MagicMock()
    mock_reader.pages = [mock_pypdf_page]

    with (
        patch("pdfplumber.open", side_effect=Exception("corrupt PDF")),
        patch("job_scout.profile.PdfReader", return_value=mock_reader),
    ):
        text = extract_text_from_pdf(dummy)

    assert text == "Pypdf extracted text"


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def test_extract_json_from_code_block() -> None:
    data = _extract_json(MOCK_LLM_JSON)
    assert data["target_titles"] == ["Software Engineer", "Backend Engineer"]
    assert data["salary_floor"] == 150000.0


def test_extract_json_raw_object() -> None:
    data = _extract_json(MOCK_LLM_JSON_RAW)
    assert data["target_titles"] == ["Data Engineer"]
    assert data["salary_floor"] is None


def test_extract_json_no_json_raises() -> None:
    with pytest.raises(ValueError, match="No JSON"):
        _extract_json("Here is my answer: the best titles are software engineer.")


# ---------------------------------------------------------------------------
# parse_resume (mocked LLM)
# ---------------------------------------------------------------------------

def test_parse_resume_code_block_response() -> None:
    with patch("job_scout.profile._create_message", return_value=MOCK_LLM_JSON):
        profile = parse_resume(
            raw_text="Jane Doe resume text.",
            target_titles=["Software Engineer"],
            seniority=["senior"],
            target_locations=["Remote"],
            salary_floor=150_000.0,
            requires_visa_sponsorship=False,
            deal_breakers=["blockchain"],
            ideal_role_description="Senior Python backend role.",
            work_artifacts=["https://github.com/user/repo"],
            client=MagicMock(),
        )

    assert profile.target_titles == ["Software Engineer", "Backend Engineer"]
    assert profile.seniority == ["senior", "staff"]
    assert profile.salary_floor == 150_000.0
    assert profile.requires_visa_sponsorship is False
    assert profile.raw_resume_text == "Jane Doe resume text."


def test_parse_resume_raw_json_response() -> None:
    with patch("job_scout.profile._create_message", return_value=MOCK_LLM_JSON_RAW):
        profile = parse_resume(
            raw_text="Resume with no salary.",
            target_titles=["Data Engineer"],
            seniority=["senior"],
            target_locations=["Remote"],
            salary_floor=None,
            requires_visa_sponsorship=True,
            deal_breakers=[],
            ideal_role_description="Data pipeline work.",
            work_artifacts=[],
            client=MagicMock(),
        )

    assert profile.salary_floor is None
    assert profile.requires_visa_sponsorship is True
    assert profile.raw_resume_text == "Resume with no salary."


def test_parse_resume_invalid_llm_response_raises() -> None:
    with (
        patch("job_scout.profile._create_message", return_value="Sorry, I cannot help."),
        pytest.raises(ValueError, match="No JSON"),
    ):
        parse_resume(
            raw_text="Resume.",
            target_titles=["SWE"],
            seniority=["senior"],
            target_locations=["Remote"],
            salary_floor=None,
            requires_visa_sponsorship=False,
            deal_breakers=[],
            ideal_role_description="Good role.",
            work_artifacts=[],
            client=MagicMock(),
        )


# ---------------------------------------------------------------------------
# Encryption / decryption
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip() -> None:
    key = Fernet.generate_key()
    profile = _make_profile()
    encrypted = encrypt_profile(profile, key)
    assert isinstance(encrypted, bytes)
    assert encrypted != profile.model_dump_json().encode()
    recovered = decrypt_profile(encrypted, key)
    assert recovered == profile


def test_decrypt_wrong_key_raises() -> None:
    key1 = Fernet.generate_key()
    key2 = Fernet.generate_key()
    profile = _make_profile()
    encrypted = encrypt_profile(profile, key1)
    with pytest.raises(Exception):
        decrypt_profile(encrypted, key2)


# ---------------------------------------------------------------------------
# save / load
# ---------------------------------------------------------------------------

def test_save_load_profile(tmp_path: Path) -> None:
    key = Fernet.generate_key()
    profile = _make_profile()
    out = tmp_path / "profile.encrypted.json"

    save_profile(profile, out, key)
    assert out.exists()

    loaded = load_profile(out, key)
    assert loaded == profile
