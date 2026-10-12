from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import get_settings
from ..exceptions import CVValidationError
from ..logging_config import get_logger

logger = get_logger("cv_parser.file_validation")

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def validate_upload(
    filename: str,
    file_bytes: bytes,
    content_type: str | None = None,
) -> str:
    """Validate a CV upload and return a SHA-256 hash of the content.

    Args:
        filename: Original filename from upload.
        file_bytes: Raw file content bytes.
        content_type: Optional MIME type from upload.

    Returns:
        SHA-256 hex digest of the file content.

    Raises:
        CVValidationError: If the file fails any validation check.
    """
    settings = get_settings()

    # Validate extension
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise CVValidationError(
            f"Unsupported file type '{suffix}'. Please upload a PDF or DOCX file."
        )

    # Validate content type if provided (do not trust alone)
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        logger.warning("Unexpected MIME type reported by client", extra={"mime": content_type})
        # Don't reject on MIME alone; we trust extension + magic bytes

    # Validate size
    max_bytes = settings.cv_max_size_bytes
    if len(file_bytes) > max_bytes:
        raise CVValidationError(
            f"File exceeds maximum size of {settings.cv_max_size_mb} MB. "
            f"Please reduce the file size and try again."
        )

    if len(file_bytes) < 100:
        raise CVValidationError("File appears to be empty or corrupted.")

    # Validate magic bytes
    if suffix == ".pdf" and not file_bytes.startswith(b"%PDF"):
        raise CVValidationError(
            "File does not appear to be a valid PDF (missing PDF header)."
        )

    # Compute hash
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    logger.info("CV file validated", extra={"ext": suffix, "size_kb": len(file_bytes) // 1024})
    return file_hash
