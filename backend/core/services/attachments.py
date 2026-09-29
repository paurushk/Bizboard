"""Shared FileAsset create for complaint, ticket, and contract uploads."""

from __future__ import annotations

from django.conf import settings

from core.exceptions import BusinessRuleError
from core.models import FileAsset

ALLOWED_CONTENT_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
})

# Leading-byte signatures, not the client-supplied Content-Type header, which
# is just a form field the caller controls — a renamed .exe with a spoofed
# header would otherwise sail through unnoticed.
_MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
)
_SNIFF_BYTES = 16  # covers every signature above, plus WebP's RIFF....WEBP


def _sniff_content_type(upload) -> str | None:
    head = upload.read(_SNIFF_BYTES)
    upload.seek(0)
    for magic, content_type in _MAGIC_SIGNATURES:
        if head.startswith(magic):
            return content_type
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def create_attachment(company, user, upload) -> FileAsset:
    if upload is None:
        raise BusinessRuleError("A file is required.")
    content_type = _sniff_content_type(upload)
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise BusinessRuleError("Upload a JPEG, PNG, WebP, or PDF file.")
    limit = int(getattr(settings, "FILE_UPLOAD_MAX_MEMORY_SIZE", 15 * 1024 * 1024))
    size = int(getattr(upload, "size", 0) or 0)
    if size > limit:
        raise BusinessRuleError("File exceeds the upload size limit.")
    return FileAsset.objects.create(
        company=company,
        kind=FileAsset.Kind.ATTACHMENT,
        file=upload,
        original_name=(getattr(upload, "name", "") or "")[:255],
        content_type=content_type,
        size=size,
        created_by=user,
        updated_by=user,
    )


def delete_join_row(queryset, attachment_id):
    """Remove the join row. The FileAsset stays (PROTECT); the link is the attachment."""
    if not attachment_id:
        raise BusinessRuleError("Attachment id is required.")
    row = queryset.filter(pk=attachment_id).first()
    if row is None:
        raise BusinessRuleError("Attachment was not found.")
    row.delete()
