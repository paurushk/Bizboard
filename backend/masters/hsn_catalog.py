"""Common GST HSN/SAC codes for the Find HSN helper (not a live GSTN feed)."""

from datetime import date

COMMON_HSN = [
    {"code": "0401", "description": "Milk and cream, not concentrated", "kind": "HSN"},
    {"code": "0402", "description": "Milk and cream, concentrated or containing sugar", "kind": "HSN"},
    {"code": "0405", "description": "Butter and other fats and oils derived from milk", "kind": "HSN"},
    {"code": "0901", "description": "Coffee, whether or not roasted or decaffeinated", "kind": "HSN"},
    {"code": "0902", "description": "Tea, whether or not flavoured", "kind": "HSN"},
    {"code": "1006", "description": "Rice", "kind": "HSN"},
    {"code": "1101", "description": "Wheat or meslin flour", "kind": "HSN"},
    {"code": "1512", "description": "Sunflower-seed, safflower or cotton-seed oil", "kind": "HSN"},
    {"code": "1701", "description": "Cane or beet sugar and chemically pure sucrose", "kind": "HSN"},
    {"code": "1704", "description": "Sugar confectionery (including white chocolate)", "kind": "HSN"},
    {"code": "1902", "description": "Pasta, couscous, whether or not prepared", "kind": "HSN"},
    {"code": "1905", "description": "Bread, pastry, cakes, biscuits and other bakers' wares", "kind": "HSN"},
    {"code": "2009", "description": "Fruit juices and vegetable juices", "kind": "HSN"},
    {"code": "2106", "description": "Food preparations not elsewhere specified", "kind": "HSN"},
    {"code": "2201", "description": "Waters, including natural or artificial mineral waters", "kind": "HSN"},
    {"code": "2202", "description": "Waters, including sweetened or flavoured", "kind": "HSN"},
    {"code": "2402", "description": "Cigars, cheroots, cigarillos and cigarettes", "kind": "HSN"},
    {"code": "2710", "description": "Petroleum oils and oils obtained from bituminous minerals", "kind": "HSN"},
    {"code": "3003", "description": "Medicaments consisting of two or more constituents mixed", "kind": "HSN"},
    {"code": "3004", "description": "Medicaments (excluding goods of heading 3002, 3005 or 3006)", "kind": "HSN"},
    {"code": "3005", "description": "Wadding, gauze, bandages and similar articles", "kind": "HSN"},
    {"code": "3304", "description": "Beauty or make-up preparations", "kind": "HSN"},
    {"code": "3305", "description": "Preparations for use on the hair", "kind": "HSN"},
    {"code": "3401", "description": "Soap; organic surface-active products", "kind": "HSN"},
    {"code": "3402", "description": "Organic surface-active agents and washing preparations", "kind": "HSN"},
    {"code": "3923", "description": "Articles for the conveyance or packing of goods, of plastics", "kind": "HSN"},
    {"code": "3924", "description": "Tableware, kitchenware, other household articles of plastics", "kind": "HSN"},
    {"code": "4010", "description": "Conveyor or transmission belts of vulcanised rubber", "kind": "HSN"},
    {"code": "4011", "description": "New pneumatic tyres, of rubber", "kind": "HSN"},
    {"code": "4818", "description": "Toilet paper, handkerchiefs, tissues and similar paper", "kind": "HSN"},
    {"code": "4819", "description": "Cartons, boxes, cases of paper or paperboard", "kind": "HSN"},
    {"code": "4901", "description": "Printed books, brochures, leaflets", "kind": "HSN"},
    {"code": "6109", "description": "T-shirts, singlets and other vests, knitted or crocheted", "kind": "HSN"},
    {"code": "6110", "description": "Jerseys, pullovers, cardigans, knitted or crocheted", "kind": "HSN"},
    {"code": "6203", "description": "Men's or boys' suits, ensembles, jackets, trousers", "kind": "HSN"},
    {"code": "6204", "description": "Women's or girls' suits, ensembles, jackets, dresses", "kind": "HSN"},
    {"code": "6403", "description": "Footwear with outer soles of rubber, plastics, leather", "kind": "HSN"},
    {"code": "7308", "description": "Structures and parts of structures of iron or steel", "kind": "HSN"},
    {"code": "8418", "description": "Refrigerators, freezers and other refrigerating equipment", "kind": "HSN"},
    {"code": "8471", "description": "Automatic data processing machines and units thereof", "kind": "HSN"},
    {"code": "8504", "description": "Electrical transformers, static converters and inductors", "kind": "HSN"},
    {"code": "8507", "description": "Electric accumulators, including separators therefor", "kind": "HSN"},
    {"code": "8517", "description": "Telephone sets, including smartphones", "kind": "HSN"},
    {"code": "8528", "description": "Monitors and projectors; television receivers", "kind": "HSN"},
    {"code": "8708", "description": "Parts and accessories of motor vehicles", "kind": "HSN"},
    {"code": "9403", "description": "Other furniture and parts thereof", "kind": "HSN"},
    {"code": "9503", "description": "Tricycles, scooters, dolls, other toys", "kind": "HSN"},
    {"code": "9619", "description": "Sanitary towels and similar articles", "kind": "HSN"},
    {"code": "9963", "description": "Accommodation, food and beverage services", "kind": "SAC"},
    {"code": "9971", "description": "Financial and related services", "kind": "SAC"},
    {"code": "9972", "description": "Real estate services", "kind": "SAC"},
    {"code": "9982", "description": "Legal and accounting services", "kind": "SAC"},
    {"code": "9983", "description": "Other professional, technical and business services", "kind": "SAC"},
    {"code": "9984", "description": "Telecommunications, broadcasting and information supply", "kind": "SAC"},
    {"code": "9985", "description": "Support services", "kind": "SAC"},
    {"code": "9986", "description": "Support services to agriculture, hunting, forestry, fishing, mining", "kind": "SAC"},
    {"code": "9987", "description": "Maintenance, repair and installation (except construction) services", "kind": "SAC"},
    {"code": "9988", "description": "Manufacturing services on physical inputs owned by others", "kind": "SAC"},
    {"code": "9989", "description": "Other manufacturing services; publishing, printing and reproduction", "kind": "SAC"},
    {"code": "9993", "description": "Public administration and other services provided to the community", "kind": "SAC"},
    {"code": "9996", "description": "Recreational, cultural and sporting services", "kind": "SAC"},
    {"code": "9997", "description": "Other services", "kind": "SAC"},
]


def search_hsn(query: str, *, kind: str | None = None, limit: int = 20) -> list[dict]:
    q = (query or "").strip().lower()
    kind = (kind or "").upper() or None
    rows = []
    for row in COMMON_HSN:
        if kind and row["kind"] != kind:
            continue
        blob = f"{row['code']} {row['description']}".lower()
        if not q or q in blob:
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


GST2_CUTOVER = date(2025, 9, 22)

# Starter table only — curator unnamed, so the product does not claim automatic GST updates.
STARTER_HSN_RATES = [
    # Biscuits / bakers' wares: 18% → 5% at GST 2.0.
    {"hsn_sac": "1905", "rate": "18", "cess": "0", "valid_from": "2017-07-01", "valid_to": "2025-09-21",
     "version": "pre-gst2.0", "source_ref": "starter-table"},
    {"hsn_sac": "1905", "rate": "5", "cess": "0", "valid_from": "2025-09-22", "valid_to": None,
     "version": "gst2.0-2025-09-22", "source_ref": "starter-table"},
    # Cigarettes: 28% → 40% sin slab.
    {"hsn_sac": "2402", "rate": "28", "cess": "0", "valid_from": "2017-07-01", "valid_to": "2025-09-21",
     "version": "pre-gst2.0", "source_ref": "starter-table"},
    {"hsn_sac": "2402", "rate": "40", "cess": "0", "valid_from": "2025-09-22", "valid_to": None,
     "version": "gst2.0-2025-09-22", "source_ref": "starter-table"},
]


def _hsn_prefixes(hsn: str) -> list[str]:
    digits = "".join(c for c in (hsn or "") if c.isdigit())
    out = []
    for length in (8, 6, 4):
        if len(digits) >= length:
            out.append(digits[:length])
    if digits and digits not in out:
        out.append(digits)
    return out


def rate_for(hsn: str, on_date) -> dict | None:
    """Return the HsnRate in force on ``on_date``, or None if the table has no row.

    None means keep the line/product rate — do not invent a rate.
    """
    from datetime import date as date_cls
    from decimal import Decimal

    from django.db.models import Q

    from masters.models import HsnRate

    if on_date is None:
        return None
    if isinstance(on_date, str):
        on_date = date_cls.fromisoformat(str(on_date)[:10])
    prefixes = _hsn_prefixes(hsn)
    if not prefixes:
        return None
    qs = (
        HsnRate.objects.filter(hsn_sac__in=prefixes)
        .filter(valid_from__lte=on_date)
        .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=on_date))
    )
    rows = list(qs)
    if not rows:
        return None
    rows.sort(key=lambda r: (len(r.hsn_sac), r.valid_from), reverse=True)
    hit = rows[0]
    return {
        "rate": Decimal(str(hit.rate)),
        "cess": Decimal(str(hit.cess or 0)),
        "version": hit.version,
        "hsn_sac": hit.hsn_sac,
        "source_ref": hit.source_ref,
    }


def seed_starter_hsn_rates() -> int:
    """Idempotent seed of the starter GST 2.0 table. Not a live Council feed."""
    from datetime import date as date_cls
    from decimal import Decimal

    from masters.models import HsnRate

    created = 0
    for row in STARTER_HSN_RATES:
        valid_from = date_cls.fromisoformat(row["valid_from"])
        valid_to = date_cls.fromisoformat(row["valid_to"]) if row["valid_to"] else None
        _, was = HsnRate.objects.get_or_create(
            hsn_sac=row["hsn_sac"],
            version=row["version"],
            defaults={
                "rate": Decimal(row["rate"]),
                "cess": Decimal(row["cess"]),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "source_ref": row["source_ref"],
            },
        )
        if was:
            created += 1
    return created
