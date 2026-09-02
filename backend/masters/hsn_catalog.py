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
    {"code": "6104", "description": "Women's or girls' suits, ensembles, jackets, trousers, knitted", "kind": "HSN"},
    {"code": "6105", "description": "Men's or boys' shirts, knitted or crocheted", "kind": "HSN"},
    {"code": "6108", "description": "Women's or girls' slips, pyjamas, nightdresses, knitted", "kind": "HSN"},
    {"code": "6204", "description": "Women's or girls' suits, ensembles, jackets, dresses", "kind": "HSN"},
    {"code": "6205", "description": "Men's or boys' shirts", "kind": "HSN"},
    {"code": "6211", "description": "Track suits, ski suits and swimwear; other garments", "kind": "HSN"},
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


def _current_starter_rate(code: str) -> str | None:
    digits = "".join(c for c in (code or "") if c.isdigit())
    prefixes = [digits[:n] for n in (8, 6, 4) if len(digits) >= n]
    for prefix in prefixes:
        hits = [r for r in STARTER_HSN_RATES if r["hsn_sac"] == prefix and r.get("valid_to") is None]
        if hits:
            return str(hits[0]["rate"])
    return None


def search_hsn(query: str, *, kind: str | None = None, limit: int = 40) -> list[dict]:
    q = (query or "").strip().lower()
    kind = (kind or "").upper() or None
    rows = []
    for row in COMMON_HSN:
        if kind and row["kind"] != kind:
            continue
        blob = f"{row['code']} {row['description']}".lower()
        if not q or q in blob:
            rows.append({
                **row,
                "gst_rate": _current_starter_rate(row["code"]),
                "chapter": row["description"],
            })
        if len(rows) >= limit:
            break
    return rows


GST2_CUTOVER = date(2025, 9, 22)
_PRE_FROM = "2017-07-01"
_PRE_TO = "2025-09-21"
_POST_FROM = "2025-09-22"
_PRE_VER = "pre-gst2.0"
_POST_VER = "gst2.0-2025-09-22"

# ---------------------------------------------------------------------------
# Curated HSN → GST rate starter table (4-digit chapter headings).
#
# DISCLAIMER: this is a best-effort convenience table at the 4-digit level for
# the goods a typical Indian SMB bills most often. It reflects the GST 2.0 rate
# rationalisation effective 22-Sep-2025 (primarily 5 / 18 / 40 slabs) and the
# earlier structure before it. It is NOT the full CBIC rate schedule, does not
# cover every 6/8-digit exception, and MUST be verified by your CA against the
# current CGST rate notifications before you rely on it for filing. `rate_for()`
# only *overrides* a line rate when a row matches; anything not listed keeps the
# rate the user / product master entered.
#
# spec row: (hsn4, pre_rate, pre_cess, post_rate, post_cess, note)
# ---------------------------------------------------------------------------
_HSN_RATE_SPEC = [
    # --- Foodstuffs, beverages (Ch. 04-24) ---
    ("0401", "5", "0", "0", "0", "Milk, fresh — nil at GST 2.0"),
    ("0402", "5", "0", "5", "0", "Milk powder / concentrated"),
    ("0405", "12", "0", "5", "0", "Butter, ghee, dairy fats"),
    ("0406", "12", "0", "5", "0", "Cheese, paneer (pre-packed)"),
    ("0701", "0", "0", "0", "0", "Potatoes, fresh"),
    ("0713", "0", "0", "0", "0", "Dried leguminous vegetables (pulses)"),
    ("0901", "5", "0", "5", "0", "Coffee"),
    ("0902", "5", "0", "5", "0", "Tea"),
    ("1006", "0", "0", "0", "0", "Rice (non-branded) — branded/packed 5%"),
    ("1101", "0", "0", "0", "0", "Wheat / meslin flour (non-branded)"),
    ("1507", "5", "0", "5", "0", "Soya-bean oil"),
    ("1512", "5", "0", "5", "0", "Sunflower / safflower / cotton-seed oil"),
    ("1517", "5", "0", "5", "0", "Edible mixtures / vanaspati"),
    ("1701", "5", "0", "5", "0", "Cane / beet sugar"),
    ("1704", "18", "0", "5", "0", "Sugar confectionery"),
    ("1806", "18", "0", "18", "0", "Chocolate & cocoa preparations"),
    ("1902", "12", "0", "5", "0", "Pasta, noodles"),
    ("1905", "18", "0", "5", "0", "Bread, biscuits, bakers' wares"),
    ("2009", "12", "0", "5", "0", "Fruit / vegetable juices"),
    ("2101", "18", "0", "18", "0", "Coffee / tea extracts, instant"),
    ("2106", "18", "0", "18", "0", "Food preparations n.e.s."),
    ("2201", "18", "0", "18", "0", "Waters / mineral waters (unsweetened 5%)"),
    ("2202", "28", "12", "40", "0", "Aerated / sweetened beverages"),
    ("2203", "28", "0", "40", "0", "Beer"),
    ("2402", "28", "0", "40", "0", "Cigars / cigarettes (+ tobacco cess)"),
    ("2403", "28", "0", "40", "0", "Other manufactured tobacco (+ cess)"),
    ("2404", "28", "0", "40", "0", "Chewing tobacco / pan masala type (+ cess)"),
    # --- Chemicals, pharma, cosmetics (Ch. 28-38) ---
    ("3003", "12", "0", "5", "0", "Medicaments (bulk / unmixed)"),
    ("3004", "12", "0", "5", "0", "Medicaments (retail packs)"),
    ("3005", "12", "0", "5", "0", "Wadding, gauze, bandages, dressings"),
    ("3006", "12", "0", "5", "0", "Pharmaceutical goods (sutures, kits)"),
    ("3208", "18", "0", "18", "0", "Paints & varnishes (non-aqueous)"),
    ("3209", "18", "0", "18", "0", "Paints & varnishes (aqueous)"),
    ("3304", "18", "0", "18", "0", "Beauty / make-up preparations"),
    ("3305", "18", "0", "18", "0", "Hair preparations"),
    ("3306", "18", "0", "18", "0", "Oral / dental hygiene"),
    ("3401", "18", "0", "18", "0", "Soap"),
    ("3402", "18", "0", "18", "0", "Detergents / washing preparations"),
    # --- Plastics, rubber, leather (Ch. 39-43) ---
    ("3917", "18", "0", "18", "0", "Plastic tubes, pipes, hoses"),
    ("3923", "18", "0", "18", "0", "Plastic packing articles"),
    ("3924", "18", "0", "18", "0", "Plastic tableware / kitchenware"),
    ("3926", "18", "0", "18", "0", "Other articles of plastics"),
    ("4011", "28", "0", "18", "0", "New pneumatic tyres"),
    ("4013", "28", "0", "18", "0", "Inner tubes of rubber"),
    ("4202", "18", "0", "18", "0", "Trunks, cases, handbags"),
    # --- Paper, printed matter (Ch. 48-49) ---
    ("4802", "12", "0", "18", "0", "Uncoated paper / paperboard"),
    ("4818", "18", "0", "18", "0", "Toilet paper, tissues, napkins"),
    ("4819", "18", "0", "18", "0", "Cartons, boxes, cases of paper"),
    ("4820", "18", "0", "18", "0", "Registers, notebooks, stationery"),
    ("4901", "0", "0", "0", "0", "Printed books"),
    ("4909", "12", "0", "18", "0", "Printed postcards / greeting cards"),
    # --- Textiles, apparel, footwear (Ch. 50-64) ---
    ("5208", "5", "0", "5", "0", "Woven cotton fabric"),
    ("5407", "5", "0", "5", "0", "Woven synthetic filament fabric"),
    ("6101", "12", "0", "5", "0", "Men's overcoats etc. (knitted)"),
    ("6109", "12", "0", "5", "0", "T-shirts, singlets (knitted)"),
    ("6110", "12", "0", "5", "0", "Jerseys, pullovers (knitted)"),
    ("6203", "12", "0", "5", "0", "Men's suits, trousers"),
    ("6204", "12", "0", "5", "0", "Women's suits, dresses"),
    ("6205", "12", "0", "5", "0", "Men's shirts"),
    ("6302", "12", "0", "5", "0", "Bed / table / kitchen linen"),
    ("6403", "18", "0", "18", "0", "Footwear, leather uppers (<=1000 5%)"),
    ("6405", "18", "0", "18", "0", "Other footwear (<=1000 5%)"),
    # --- Stone, ceramics, glass (Ch. 68-70) ---
    ("6802", "18", "0", "18", "0", "Worked monumental / building stone"),
    ("6907", "18", "0", "18", "0", "Ceramic tiles / flags"),
    ("6910", "18", "0", "18", "0", "Ceramic sinks, wash basins, sanitary"),
    ("7013", "18", "0", "18", "0", "Glassware for table / kitchen"),
    # --- Base metals & articles (Ch. 72-83) ---
    ("7210", "18", "0", "18", "0", "Flat-rolled iron/steel, plated/coated"),
    ("7214", "18", "0", "18", "0", "Bars & rods of iron / non-alloy steel"),
    ("7308", "18", "0", "18", "0", "Structures & parts, iron or steel"),
    ("7317", "18", "0", "18", "0", "Nails, tacks, staples of iron/steel"),
    ("7323", "18", "0", "18", "0", "Table / kitchen articles of iron/steel"),
    ("7610", "18", "0", "18", "0", "Aluminium structures"),
    ("8302", "18", "0", "18", "0", "Base metal mountings / fittings"),
    ("8481", "18", "0", "18", "0", "Taps, cocks, valves"),
    # --- Machinery & electrical (Ch. 84-85) ---
    ("8413", "18", "0", "18", "0", "Pumps for liquids"),
    ("8414", "18", "0", "18", "0", "Air / vacuum pumps, compressors, fans"),
    ("8415", "28", "0", "18", "0", "Air-conditioning machines"),
    ("8418", "28", "0", "18", "0", "Refrigerators, freezers"),
    ("8421", "18", "0", "18", "0", "Centrifuges, filtering machinery"),
    ("8443", "18", "0", "18", "0", "Printing / copying machinery"),
    ("8450", "18", "0", "18", "0", "Household washing machines"),
    ("8471", "18", "0", "18", "0", "Computers & data-processing units"),
    ("8481", "18", "0", "18", "0", "Valves / taps (machinery)"),
    ("8504", "18", "0", "18", "0", "Transformers, static converters, chargers"),
    ("8507", "18", "0", "18", "0", "Electric accumulators / batteries"),
    ("8517", "18", "0", "18", "0", "Telephones incl. smartphones"),
    ("8523", "18", "0", "18", "0", "Discs, tapes, solid-state storage"),
    ("8528", "28", "0", "18", "0", "Monitors, projectors, TV receivers"),
    ("8536", "18", "0", "18", "0", "Electrical switches, plugs, sockets"),
    ("8544", "18", "0", "18", "0", "Insulated wire & cable"),
    # --- Vehicles (Ch. 87) — compensation cess on many ---
    ("8703", "28", "17", "40", "0", "Motor cars (cess varies by engine/length)"),
    ("8711", "28", "0", "40", "0", "Motorcycles (>350cc historically +3% cess)"),
    ("8712", "12", "0", "5", "0", "Bicycles, non-motorised"),
    ("8714", "18", "0", "18", "0", "Parts & accessories of cycles"),
    # --- Furniture, toys, misc (Ch. 94-96) ---
    ("9401", "18", "0", "18", "0", "Seats / chairs"),
    ("9403", "18", "0", "18", "0", "Other furniture"),
    ("9404", "18", "0", "5", "0", "Mattresses, quilts, bedding"),
    ("9405", "18", "0", "18", "0", "Lamps & lighting fittings"),
    ("9503", "18", "0", "18", "0", "Tricycles, scooters, toys"),
    ("9506", "18", "0", "18", "0", "Sports goods / gym equipment"),
    ("9603", "18", "0", "18", "0", "Brooms, brushes"),
    ("9619", "12", "0", "5", "0", "Sanitary towels, napkins, diapers"),
]

# Common SAC (services) — mostly 18%, some 5% without ITC.
_SAC_RATE_SPEC = [
    ("9963", "18", "0", "18", "0", "Accommodation, food & beverage services"),
    ("9964", "18", "0", "18", "0", "Passenger transport (varies; some 5%)"),
    ("9965", "18", "0", "18", "0", "Goods transport (GTA 5%/12%/18%)"),
    ("9971", "18", "0", "18", "0", "Financial & related services"),
    ("9972", "18", "0", "18", "0", "Real estate services"),
    ("9973", "18", "0", "18", "0", "Leasing / rental services"),
    ("9982", "18", "0", "18", "0", "Legal & accounting services"),
    ("9983", "18", "0", "18", "0", "Other professional / technical / business"),
    ("9984", "18", "0", "18", "0", "Telecom, broadcasting, information supply"),
    ("9985", "18", "0", "18", "0", "Support services"),
    ("9987", "18", "0", "18", "0", "Maintenance, repair & installation"),
    ("9988", "12", "0", "5", "0", "Manufacturing services on others' inputs (job work)"),
    ("9989", "18", "0", "18", "0", "Other manufacturing / publishing / printing"),
    ("9994", "18", "0", "18", "0", "Sewage, waste collection & sanitation"),
    ("9997", "18", "0", "18", "0", "Other services"),
]


def _build_starter_rates():
    rows = []
    for spec in (_HSN_RATE_SPEC + _SAC_RATE_SPEC):
        hsn, pre_r, pre_c, post_r, post_c, _note = spec
        rows.append({
            "hsn_sac": hsn, "rate": pre_r, "cess": pre_c,
            "valid_from": _PRE_FROM, "valid_to": _PRE_TO,
            "version": _PRE_VER, "source_ref": "starter-table",
        })
        # Only add a post-cutover row when the rate or cess actually changed,
        # else the pre row (with valid_to) would leave a gap after the cutover —
        # so for unchanged HSNs the post row keeps the same rate, open-ended.
        rows.append({
            "hsn_sac": hsn, "rate": post_r, "cess": post_c,
            "valid_from": _POST_FROM, "valid_to": None,
            "version": _POST_VER, "source_ref": "starter-table",
        })
    return rows


STARTER_HSN_RATES = _build_starter_rates()


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
