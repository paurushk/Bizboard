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
            *_IMAGE,
        },
    ),
    FileAsset.Kind.EXPORT: (20 * 1024 * 1024, {"text/csv", "application/pdf", "text/plain"}),
    FileAsset.Kind.ATTACHMENT: (
        10 * 1024 * 1024,
        {"application/pdf", "text/csv", "text/plain", *_IMAGE},
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


CSV_UTF8_HINT = (
    "This CSV isn't UTF-8 — in Excel use File → Save As → CSV UTF-8 (Comma delimited)."
)


def _looks_like_text_csv(header: bytes) -> bool:
    """True when the first bytes are CSV-ish text (ASCII, UTF-8, or Windows-1252)."""
    if not header:
        return False
    sample = header[:32]
    # Excel "CSV UTF-8" writes a BOM; strip it before further checks.
    if sample.startswith(b"\xef\xbb\xbf"):
        sample = sample[3:]
        if not sample:
            return True
    # Reject known binary magics that can appear if extension is wrong.
    if sample.startswith((b"%PDF", b"\x89PNG", b"PK", b"\xd0\xcf\x11\xe0")):
        return False
    if sample[:3] == b"\xff\xd8\xff":
        return False
    # Pure ASCII / tab / CR / LF — classic CSV.
    if all(b in (9, 10, 13) or 32 <= b < 127 for b in sample):
        return True
    # UTF-8 multi-byte (Devanagari, ₹, ñ, é, …) in the early bytes.
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    # Excel's default "CSV (Comma delimited)" is Windows-1252/ANSI. High bytes
    # like 0xE9 ('é') are valid there — reject NULs and other C0 controls so
    # we still don't accept binary payloads as CSV.
    if b"\x00" in sample:
        return False
    if any(b < 32 and b not in (9, 10, 13) for b in sample):
        return False
    return any(b in sample for b in (9, 10, 13, 44))


def _sniff_mime(header: bytes, filename: str, declared: str) -> str:
    declared = (declared or "").lower().split(";")[0].strip()
    name = (filename or "").lower()
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
    if header.startswith(b"PK"):
        # Only treat as XLSX when the filename says so. Bare ZIP/DOCX/PPTX
        # also start with PK and must not pass spreadsheet MIME checks.
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return ""
    if header.startswith(b"\xd0\xcf\x11\xe0"):
        return "application/vnd.ms-excel"

    # Text CSV: declared text/csv|plain, or .csv with vague/Windows Excel ctypes.
    csv_declared = declared in {
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "",
    }
    if csv_declared and _looks_like_text_csv(header):
        if declared in {"text/csv", "text/plain"}:
            return declared if declared else "text/csv"
        if name.endswith(".csv") or declared in {
            "application/vnd.ms-excel",
            "application/octet-stream",
            "",
        }:
            # Prefer text/csv over ms-excel when payload is clearly text (not OLE).
            return "text/csv"
    if name.endswith(".csv") and _looks_like_text_csv(header):
        return "text/csv"
    if name.endswith(".txt") and _looks_like_text_csv(header):
        return "text/plain"
    return ""


class FileService:
    @staticmethod
    def _clamav_scan(uploaded_file) -> None:
        """Scan when CLAMAV_HOST is set; fail-closed if the daemon is down."""
        import logging
        import socket

        from django.conf import settings

        host = (getattr(settings, "CLAMAV_HOST", None) or "").strip()
        if not host:
            return
        port = int(getattr(settings, "CLAMAV_PORT", 3310) or 3310)
        logger = logging.getLogger("bizboard.clamav")
        try:
            pos = uploaded_file.tell()
            data = uploaded_file.read()
            uploaded_file.seek(pos)
        except Exception:
            data = b""
        try:
            with socket.create_connection((host, port), timeout=3) as sock:
                sock.sendall(b"zINSTREAM\0")
                # chunked stream
                chunk = data or b"\x00"
                size = len(chunk).to_bytes(4, "big")
                sock.sendall(size + chunk)
                sock.sendall((0).to_bytes(4, "big"))
                resp = sock.recv(4096).decode("utf-8", errors="replace")
            if "FOUND" in resp.upper():
                raise BusinessRuleError("Upload blocked: malware detected by ClamAV.")
        except BusinessRuleError:
            raise
        except Exception as exc:
            # BB-000631: fail-closed when a ClamAV host is configured.
            raise BusinessRuleError(
                f"Upload blocked: malware scanner unavailable ({exc})."
            ) from exc

    @staticmethod
    def validate_upload(*, uploaded_file, kind=FileAsset.Kind.ATTACHMENT):
        rules = _KIND_RULES.get(kind) or _KIND_RULES[FileAsset.Kind.ATTACHMENT]
        max_size, allowed = rules
        size = getattr(uploaded_file, "size", 0) or 0
        if size <= 0:
            raise BusinessRuleError("Empty file uploads are not allowed.")
        if size > max_size:
            raise BusinessRuleError(f"File exceeds maximum size of {max_size // (1024 * 1024)} MB.")

        FileService._clamav_scan(uploaded_file)

        header = b""
        try:
            pos = uploaded_file.tell()
            header = uploaded_file.read(32)
            uploaded_file.seek(pos)
        except Exception:
            header = b""

        declared = getattr(uploaded_file, "content_type", "") or ""
        sniffed = _sniff_mime(header, getattr(uploaded_file, "name", "") or "", declared)
        if sniffed == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            FileService._assert_real_xlsx(uploaded_file)
        if not sniffed or sniffed not in allowed or sniffed == "application/octet-stream":
            name = (getattr(uploaded_file, "name", "") or "").lower()
            # .csv whose header has high bytes that aren't UTF-8 and didn't look
            # CSV-shaped enough to sniff — tell the user to re-save as UTF-8
            # rather than implying the file type itself is wrong.
            if name.endswith(".csv") and header and b"\x00" not in header[:32]:
                sample = header[:32]
                ascii_ok = all(b in (9, 10, 13) or 32 <= b < 127 for b in sample)
                if not ascii_ok:
                    try:
                        sample.decode("utf-8")
                    except UnicodeDecodeError:
                        raise BusinessRuleError(CSV_UTF8_HINT)
            raise BusinessRuleError(
                f"File type '{sniffed or declared or 'unknown'}' is not allowed."
            )
        return sniffed

    @staticmethod
    def _assert_real_xlsx(uploaded_file) -> None:
        """Reject ZIP/DOCX pretending to be xlsx and cap uncompressed size."""
        import zipfile

        pos = uploaded_file.tell()
        try:
            with zipfile.ZipFile(uploaded_file) as zf:
                names = set(zf.namelist())
                if "xl/workbook.xml" not in names:
                    raise BusinessRuleError("File is not a valid Excel workbook.")
                if len(names) > 2000:
                    raise BusinessRuleError("Spreadsheet has too many entries.")
                uncompressed = sum(info.file_size for info in zf.infolist())
                if uncompressed > 50 * 1024 * 1024:
                    raise BusinessRuleError("Spreadsheet uncompressed size is too large.")
        except BusinessRuleError:
            raise
        except (zipfile.BadZipFile, OSError, ValueError) as exc:
            raise BusinessRuleError("File is not a valid Excel workbook.") from exc
        finally:
            try:
                uploaded_file.seek(pos)
            except Exception:
                pass

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
        # BB-000644: same validation path as store_upload.
        uploaded = ContentFile(content, name=filename)
        uploaded.content_type = content_type or ""
        sniffed = FileService.validate_upload(uploaded_file=uploaded, kind=kind)
        return FileAsset.objects.create(
            company=company,
            kind=kind,
            file=uploaded,
            original_name=filename,
            content_type=sniffed or content_type,
            size=len(content),
            created_by=user,
            updated_by=user,
        )
