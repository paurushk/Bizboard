"""Deterministic matching of what a customer wrote to the company's masters (plan AGT-304).

Order of trust for a product: learned alias, then SKU/barcode, then exact name, then fuzzy name. A fuzzy
match is accepted on its own only when it clears a threshold and beats the runner-up by a margin;
otherwise the line stays unresolved with up to three alternatives for the person to pick. Customers are
matched the same way, plus phone number. The model never supplies an id or a price.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from .parsing import normalize, phones_in

ACCEPT = 0.84
MARGIN = 0.08
FLOOR = 0.55
MAX_ALTERNATIVES = 3
MAX_CATALOGUE = 20000


def _score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jaccard = len(ta & tb) / len(ta | tb) if ta and tb else 0.0
    # Every word the customer wrote is (nearly) a word of the name, in any order: "atta aashirvaad", "sugr bag".
    token = 0.0
    if ta and tb and all(len(w) >= 2 for w in ta):
        best = [max(SequenceMatcher(None, w, v).ratio() for v in tb) for w in ta]
        if min(best) >= 0.8:
            token = 0.8 + 0.2 * (len(ta) / len(tb)) * (sum(best) / len(best))
    contains = 0.9 if (a in b or b in a) and min(len(a), len(b)) >= 3 else 0.0
    return max(SequenceMatcher(None, a, b).ratio(), jaccard, token, contains * min(1.0, 0.6 + 0.4 * jaccard + 0.2 * (len(a) > 3)))


def _pick(scored: list[tuple[float, int, str]]) -> tuple[dict | None, list[dict]]:
    scored = sorted(scored, key=lambda t: (-t[0], t[1]))
    alts = [{"id": i, "name": n, "score": round(s, 3)} for s, i, n in scored if s >= FLOOR][:MAX_ALTERNATIVES]
    if not scored:
        return None, alts
    top = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if top[0] >= ACCEPT and top[0] - runner >= MARGIN:
        return {"id": top[1], "name": top[2], "score": round(top[0], 3)}, alts
    return None, alts


# --- customers ---------------------------------------------------------------------------------
def resolve_customer(company, hint: str, text: str = "") -> dict:
    """{id, name, match:{source, score}, alternatives}. ``id`` is None when ambiguous or unknown."""
    from agents.models import AgentAlias
    from masters.models import Customer

    norm = normalize(hint)
    if norm:
        alias = (
            AgentAlias.objects.filter(company=company, scope=AgentAlias.SCOPE_CUSTOMER, raw_text_norm=norm)
            .select_related("customer").first()
        )
        if alias and alias.customer and not alias.customer.is_deleted:
            return _found(alias.customer, "alias", 1.0)
        # A name the sender gave wins over a phone number somewhere in the text, which may be a delivery contact.
        rows = list(Customer.objects.filter(company=company).values_list("id", "name")[:MAX_CATALOGUE])
        exact = [(i, n) for i, n in rows if normalize(n) == norm]
        if len(exact) == 1:
            return {"id": exact[0][0], "name": exact[0][1], "match": {"source": "name", "score": 1.0}, "alternatives": []}
    for phone in phones_in(f"{hint}\n{text}"):
        hits = list(Customer.objects.filter(company=company, phone__endswith=phone[-10:])[:2])
        if len(hits) == 1:
            return _found(hits[0], "phone", 1.0)
    if not norm:
        return {"id": None, "name": "", "match": {"source": "none", "score": 0}, "alternatives": []}
    picked, alts = _pick([(_score(norm, normalize(n)), i, n) for i, n in rows])
    if picked:
        return {"id": picked["id"], "name": picked["name"], "match": {"source": "fuzzy", "score": picked["score"]}, "alternatives": alts}
    return {"id": None, "name": "", "match": {"source": "none", "score": 0}, "alternatives": alts}


def _found(customer, source: str, score: float) -> dict:
    return {"id": customer.id, "name": customer.name, "match": {"source": source, "score": score}, "alternatives": []}


# --- products ----------------------------------------------------------------------------------
class ProductIndex:
    """The company's active goods, loaded once per run."""

    def __init__(self, company):
        from masters.models import Product

        self.company = company
        qs = Product.objects.filter(company=company, status=Product.Status.ACTIVE).values_list("id", "name", "sku", "barcode")
        rows = list(qs[:MAX_CATALOGUE + 1])
        self.truncated = len(rows) > MAX_CATALOGUE  # more products than the matcher holds: say so instead of missing silently
        self.rows = [(i, n, normalize(n), (s or "").strip().lower(), (b or "").strip().lower()) for i, n, s, b in rows[:MAX_CATALOGUE]]
        self._aliases = None

    def aliases(self) -> dict[str, int]:
        if self._aliases is None:
            from agents.models import AgentAlias

            self._aliases = dict(
                AgentAlias.objects.filter(company=self.company, scope=AgentAlias.SCOPE_PRODUCT, product__isnull=False)
                .values_list("raw_text_norm", "product_id")
            )
        return self._aliases

    def name_of(self, product_id: int) -> str:
        return next((n for i, n, *_ in self.rows if i == product_id), "")

    def resolve(self, hint: str) -> dict:
        norm = normalize(hint)
        empty = {"id": None, "name": "", "match": {"source": "none", "score": 0}, "alternatives": []}
        if not norm:
            return empty
        pid = self.aliases().get(norm)
        if pid and self.name_of(pid):
            return {"id": pid, "name": self.name_of(pid), "match": {"source": "alias", "score": 1.0}, "alternatives": []}
        raw = hint.strip().lower()
        codes = [(i, n) for i, n, _nn, sku, bar in self.rows if raw and raw in (sku, bar)]
        if len(codes) == 1:
            return {"id": codes[0][0], "name": codes[0][1], "match": {"source": "code", "score": 1.0}, "alternatives": []}
        exact = [(i, n) for i, n, nn, *_ in self.rows if nn == norm]
        if len(exact) == 1:
            return {"id": exact[0][0], "name": exact[0][1], "match": {"source": "name", "score": 1.0}, "alternatives": []}
        picked, alts = _pick([(_score(norm, nn), i, n) for i, n, nn, *_ in self.rows])
        if picked:
            return {"id": picked["id"], "name": picked["name"], "match": {"source": "fuzzy", "score": picked["score"]}, "alternatives": alts}
        return {**empty, "alternatives": alts}
