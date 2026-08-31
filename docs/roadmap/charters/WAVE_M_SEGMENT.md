# Charter stub — Wave M (copy, do not fill in the abstract)

**Copy this file to** `WAVE_M_DISTRIBUTOR.md` **or** `WAVE_M_PHARMA.md` **when the first paying
customer in that segment is ready to sign.** Do not pick a segment without a customer. A blank
charter = Wave M never starts.

Use the general template in [`_TEMPLATE.md`](_TEMPLATE.md) plus the fields below.

```markdown
# Charter: WAVE_M_<DISTRIBUTOR | PHARMA>

- **PM:**
- **Date signed:**
- **Eng:**
- **CA (scheme GL + free-goods COGS — required for M-01 posting):**
- **Drug-licence consultant (pharma only):**

## Segment (exactly one)
- [ ] Distributor  → tickets in: **M-01, M-02, M-04**. M-03 is **out** (later separate charter).
- [ ] Pharma       → tickets in: **M-01, M-03, M-04**. M-02 **only if this customer runs vans**.

## Named companies
| company_id | legal name | GSTIN | plan slug |
|---|---|---|---|
| | | | |

## Written demand
Paying-customer request (email/ticket). Log in `demand-log.md`.

## Pricing tier
Which `billing.Plan.slug` unlocks `ENABLE_SCHEMES` / `ENABLE_FIELD_SALES` / `ENABLE_PHARMA`?

## Golden fixtures (M-01 DoD)
10–20 real historical Marg (or Busy) invoices: PDF **and** the scheme that produced each.
Without this pack, M-01 DoD softens to "matches a CA-reviewed manual calculation."

| Invoice no. | Date | Scheme type | Fixture files |
|---|---|---|---|
| | | | |

## CA-signed GL codes (M-01 — BLOCKED until filled)
| Purpose | Account code | Signed |
|---|---|---|
| Scheme liability | | |
| Free-goods COGS | | |
| Breakage / expiry write-off (pharma) | | |

Input-ITC reversal on FOC qty: flagged in product, **not enforced** in v1 (CA call).

## Pharma-only
- Beachhead state (v1 also includes Maharashtra): ________
- Schedule-H / H1 **column list** (signed): attach or paste
- Van sales (M-02): [ ] yes  [ ] no

## In scope / out of scope
v1 schemes: buy-X-get-Y, qty/value slab, one QPS, free goods at cost, settlement CN.
Out: multi-level hierarchies, principal claim portals, scheme-on-scheme, van warehouse, GPS.

## Success metric
One full month on BizBoard matching the M-wave exit for this segment.

## Exit criteria
- [ ] Matches WAVES_M_TO_S Wave M exit for this segment
- [ ] Demo seed flags off
- [ ] Honesty: no van-stock claim if M-02 is order-taking only
```
