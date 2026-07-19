"""File Service — logos, invoice PDFs, attachments, import files (E0.14)."""

from django.core.files.base import ContentFile

from core.models import FileAsset


class FileService:
    @staticmethod
    def store_upload(*, company, uploaded_file, kind=FileAsset.Kind.ATTACHMENT, user=None):
        return FileAsset.objects.create(
            company=company,
            kind=kind,
            file=uploaded_file,
            original_name=uploaded_file.name,
            content_type=getattr(uploaded_file, "content_type", "") or "",
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
