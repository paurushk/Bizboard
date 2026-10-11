"""Amounts in Hindi words, Indian grouping (hazaar, lakh, crore), for receipt vouchers.

Hindi has a distinct word for every number from 0 to 99, so the table is spelled out
rather than built from parts.
"""

from decimal import ROUND_HALF_UP, Decimal

_UNDER_100 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ "
    "दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस "
    "तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चौवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
    "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
    "नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()

assert len(_UNDER_100) == 100

# (divisor, word), largest first
_UNITS = ((10_000_000, "करोड़"), (100_000, "लाख"), (1_000, "हज़ार"), (100, "सौ"))


def _words(n: int) -> str:
    if n < 100:
        return _UNDER_100[n]
    parts: list[str] = []
    for divisor, word in _UNITS:
        count, n = divmod(n, divisor)
        if count:
            parts.append(f"{_words(count)} {word}")
    if n:
        parts.append(_UNDER_100[n])
    return " ".join(parts)


def amount_in_words_hi(value) -> str:
    """e.g. 125000.50 -> 'एक लाख पच्चीस हज़ार रुपये और पचास पैसे मात्र'."""
    amount = abs(Decimal(str(value))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    text = f"{_words(rupees)} रुपये"
    if paise:
        text += f" और {_words(paise)} पैसे"
    return f"{text} मात्र"
