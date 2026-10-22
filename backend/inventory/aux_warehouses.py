"""The company's quarantine and scrap godowns, made on first use (shared by manufacturing and quality)."""

from .models import Warehouse


def ensure_aux_warehouse(company, kind) -> Warehouse:
    found = Warehouse.objects.filter(company=company, kind=kind, is_active=True).order_by("id").first()
    if found:
        return found
    code, name = {"QUARANTINE": ("QRN", "Quarantine / Rework"), "SCRAP": ("SCR", "Scrap")}[kind]
    base, n = code, 1
    while Warehouse.all_objects.filter(company=company, code=code).exists():
        n += 1
        code = f"{base}{n}"
    return Warehouse.objects.create(company=company, name=name, code=code, kind=kind)
