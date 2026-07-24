"""File Service — logos, invoice PDFs, attachments, import files (E0.14)."""

from core.exceptions import BusinessRuleError
from django.core.files.base import ContentFile

from core.models import FileAsset

# kind → (max_bytes, allowed content-type prefixes / exact)
_IMAGE = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
_KIND_RULES = {
    FileAsset.Kind.LOGO: (5 * 1024 * 1024, _IMAGE),
    FileAsset.Kind.INVOICE_PDF: (20 * 1024 * 1024, {"application/pdf"}),
    FileAsset.Kind.IMPORT: (
        10 * 1024 * 1024,
        {
            "text/csv",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain",
            "application/pdf",
            "application/octet-stream",  # browsers sometimes omit real MIME; sniff/ext still apply
            *_IMAGE,
        },
    ),
    FileAsset.Kind.EXPORT: (20 * 1024 * 1024, {"text/csv", "application/pdf", "text/plain"}),
    FileAsset.Kind.ATTACHMENT: (
        10 * 1024 * 1024,
        {"application/pdf", "text/csv", "text/plain", "application/octet-stream", *_IMAGE},
    ),
}

_EXT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _sniff_mime(header: bytes, filename: str, declared: str) -> str:
    name = (filename or "").lower()
    declared = (declared or "").lower().split(";")[0].strip()
    if header.startswith(b"%PDF"):
        return "application/pdf"
    if header.startswith(b"\x89PNG"):
        return "image/png"
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header.startswith(b"RIFF") and b"WEBP" in header[:16]:
        return "image/webp"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "image/gif"
    for ext, mime in _EXT_MIME.items():
        if name.endswith(ext):
            return mime
    return declared


class FileService:
    @staticmethod
    def validate_upload(*, uploaded_file, kind=FileAsset.Kind.ATTACHMENT):
        rules = _KIND_RULES.get(kind) or _KIND_RULES[FileAsset.Kind.ATTACHMENT]
        max_size, allowed = rules
        size = getattr(uploaded_file, "size", 0) or 0
        if size <= 0:
            raise BusinessRuleError("Empty file uploads are not allowed.")
        if size > max_size:
            raise BusinessRuleError(f"File exceeds maximum size of {max_size // (1024 * 1024)} MB.")

        header = b""
        try:
            pos = uploaded_file.tell()
            header = uploaded_file.read(32)
            uploaded_file.seek(pos)
        except Exception:
            header = b""

        declared = getattr(uploaded_file, "content_type", "") or ""
        sniffed = _sniff_mime(header, getattr(uploaded_file, "name", "") or "", declared)
        declared_norm = declared.lower().split(";")[0].strip()
        # octet-stream is only OK when extension/sniff resolved to a real allowed type
        if sniffed == "application/octet-stream" or declared_norm == "application/octet-stream":
            if sniffed in allowed and sniffed != "application/octet-stream":
                return sniffed
            raise BusinessRuleError(
                f"File type '{sniffed or declared or 'unknown'}' is not allowed."
            )
        if sniffed not in allowed and declared_norm not in allowed:
            raise BusinessRuleError(f"File type '{sniffed or declared or 'unknown'}' is not allowed.")
        return sniffed or declared_norm

    @staticmethod
    def store_upload(*, company, uploaded_file, kind=FileAsset.Kind.ATTACHMENT, user=None):
        content_type = FileService.validate_upload(uploaded_file=uploaded_file, kind=kind)
        return FileAsset.objects.create(
            company=company,
            kind=kind,
            file=uploaded_file,
            original_name=uploaded_file.name,
            content_type=content_type or getattr(uploaded_file, "content_type", "") or "",
            size=uploaded_file.size,
            created_by=user,
            updated_by=user,
        )

    @staticmethod
    def store_bytes(*, company, content: bytes, filename: str, kind, content_type="", user=None):
        return FileAsset.objects.create(
            company=company,
            kind=kind,
            file=ContentFile(content, name=filename),
            original_name=filename,
            content_type=content_type,
            size=len(content),
            created_by=user,
            updated_by=user,
        )
