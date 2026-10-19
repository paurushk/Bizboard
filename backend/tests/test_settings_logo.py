"""SET-17: the logo flow the Company page uses: store the image, point the company at it, remove it."""

import base64

from django.core.files.uploadedfile import SimpleUploadedFile

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _upload(client, name="logo.png", data=PNG, ctype="image/png"):
    return client.post(
        "/api/v1/files/", {"kind": "LOGO", "file": SimpleUploadedFile(name, data, content_type=ctype)}, format="multipart"
    )


def test_upload_set_and_remove_logo(tenant_a):
    up = _upload(tenant_a.client)
    assert up.status_code == 201, up.data
    asset_id = up.data["id"]
    r = tenant_a.client.patch("/api/v1/company/", {"logo": asset_id}, format="json")
    assert r.status_code == 200, r.data
    assert tenant_a.client.get("/api/v1/company/").data["logo"] == asset_id
    cleared = tenant_a.client.patch("/api/v1/company/", {"logo": None}, format="json")
    assert cleared.status_code == 200, cleared.data
    assert tenant_a.client.get("/api/v1/company/").data["logo"] is None


def test_a_text_file_is_refused_as_a_logo(tenant_a):
    r = _upload(tenant_a.client, "logo.png", b"not an image at all", "image/png")
    assert r.status_code == 400, r.data


def test_another_companys_logo_cannot_be_used(tenant_a, tenant_b):
    other = _upload(tenant_b.client).data["id"]
    r = tenant_a.client.patch("/api/v1/company/", {"logo": other}, format="json")
    assert r.status_code == 400, r.data
