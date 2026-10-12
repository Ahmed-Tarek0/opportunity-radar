
import pytest

from opportunity_radar.cv_parser.file_validation import validate_upload
from opportunity_radar.exceptions import CVValidationError


def test_validate_upload_rejects_unsupported_extension():
    with pytest.raises(CVValidationError, match="Unsupported file type"):
        validate_upload("resume.txt", b"some content" * 100)


def test_validate_upload_rejects_oversized_file():
    import os
    os.environ["CV_MAX_SIZE_MB"] = "1"
    from opportunity_radar.config import get_settings
    get_settings.cache_clear()

    large_content = b"%PDF" + b"x" * (2 * 1024 * 1024)  # 2MB
    with pytest.raises(CVValidationError, match="maximum size"):
        validate_upload("resume.pdf", large_content)
    get_settings.cache_clear()


def test_validate_upload_rejects_empty_file():
    with pytest.raises(CVValidationError, match="empty"):
        validate_upload("resume.pdf", b"")


def test_validate_upload_rejects_fake_pdf():
    with pytest.raises(CVValidationError, match="valid PDF"):
        validate_upload("resume.pdf", b"not a pdf content here" * 10)


def test_validate_upload_accepts_valid_pdf():
    # Create a minimal PDF-like header
    content = b"%PDF-1.4\n" + b"fake pdf content" * 100
    result = validate_upload("resume.pdf", content)
    assert len(result) == 64  # SHA-256 hex digest


def test_validate_upload_accepts_docx():
    # DOCX files don't start with %PDF, just need extension check
    content = b"PK" + b"x" * 200  # ZIP-like content (DOCX is a ZIP)
    result = validate_upload("resume.docx", content)
    assert len(result) == 64


def test_heuristic_profile_extraction():
    from opportunity_radar.cv_parser.profile_extractor import extract_profile_from_text
    cv_text = """
    John Doe
    Senior Python Developer

    Experience:
    - 5 years of Python development
    - Django, FastAPI, PostgreSQL
    - Docker, AWS

    Projects:
    - Built an e-commerce platform using Django and React

    Education:
    - BSc Computer Science, Cairo University, 2018
    """
    # Without LLM provider
    profile = extract_profile_from_text(cv_text, llm_provider=None)
    assert profile is not None
    # Should find Python at minimum
    skill_names = profile.skill_names()
    assert "python" in skill_names
    # Should suggest some target titles
    assert len(profile.target_titles) > 0
    # Should note it used heuristics
    assert any("heuristic" in f.lower() or "llm" in f.lower()
               for f in profile.fields_needing_confirmation)
