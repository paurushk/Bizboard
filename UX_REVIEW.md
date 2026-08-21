> **Historical / superseded (2026-08-03):** See docs/reviews/ for the live engineering audit.

# BizBoard — UX REVIEW

**Date:** 2026-07-24  
**Personas:** Shop owner, sales staff, first-time GST user  

---

## Overall UX verdict

Billing screens feel **purpose-built for Indian traders** (Bill To, HSN, GST type, round-off, amount received, barcode search, shortcuts). Navigation is clear. Several labels and permission failures will confuse owners under pressure at the counter.

**UX score: 7.0 / 10**

---

## What works well

1. **New Invoice / New Purchase** mirror each other — learn once.  
2. **Save / Save & New / Save draft disabled** until party+lines — prevents empty docs.  
3. **Keyboard shortcuts dialog** present (`aria-label="shortcuts"`).  
4. **Inline create party / create item** reduces context switching.  
5. **Dashboard empty state** (“Nothing here yet”) is friendly.  
6. **Role badge + Sign out** visible in nav.  
7. **Upload Bill** linked from purchase header — discovery OK.  
8. Products table shows GST% and sale price clearly.

---

## UX issues

| ID | Severity | Issue | Screen | Suggestion |
|----|----------|-------|--------|------------|
| U-01 | High | Forbidden routes silently bounce to `/` | RoleRoute | Show “You don’t have access” toast/page |
| U-02 | High | Preview totals may ≠ saved GST | New Invoice | Fix calc parity; show “final on save” if needed |
| U-03 | Medium | “+ Discount” with “- ₹” | Invoice totals | Rename “Invoice discount (after tax)” |
| U-04 | Medium | Payment Details dismissible with × | New Invoice | Persist or explain why dismissible |
| U-05 | Medium | Invoice number editable before assign | New Invoice | Read-only “Next: INV-00007” until complete |
| U-06 | Medium | Customer list shows Walk-in only until search | New Invoice | Placeholder “Type to search customers” |
| U-07 | Medium | No aging on receivables | Dashboard/Ledger | Add Due / Overdue chips |
| U-08 | Medium | Advances not labeled | Ledger/Receipts | Tag unallocated as Advance |
| U-09 | Low | Icon-only toolbar buttons | Billing | Ensure tooltips + aria everywhere |
| U-10 | Low | Hard-coded Bengaluru T&Cs | Purchase | Company-default terms from settings |
| U-11 | Low | Dense totals panel on mobile | Billing | Stack sections; sticky grand total (mobile UAT pending) |
| U-12 | Low | Share WhatsApp = link only | Detail | Set expectation in UI copy |

---

## Workflow click-depth (shop owner)

| Task | Approx clicks | Assessment |
|------|---------------|------------|
| Create GST invoice (known customer+item) | ~6–10 | Acceptable |
| Record partial payment on existing invoice | History → detail → receipt flow | Verify one-screen pay CTA |
| Purchase + stock | New purchase complete | Good |
| Fix wrong completed invoice | Edit lines or return | Prefer guided Credit Note later |
| Staff hits Settings | Redirect home | Confusing |

---

## Accessibility

| Check | Observation |
|-------|-------------|
| Labels on major fields | Present (Customer, dates, etc.) |
| Combobox roles | MUI Autocomplete — OK |
| Screen reader | Partial; not fully audited with NVDA/VoiceOver |
| Keyboard | Shortcuts dialog exists; full tab-order audit incomplete |
| Focus management in dialogs | MUI default — likely OK |
| Color-only status | Status chips used — verify text+color |

---

## Semantic questions

| Question | Answer |
|----------|--------|
| Would a shop owner understand the main path? | **Yes**, if GST-aware |
| Too many clicks for counter billing? | **Borderline** — OK for desktop; POS mode still Phase 2 |
| Can users lose money accidentally? | **Yes** — cancel, completed line edits, post-tax discount confusion |
| Misleading? | Discount label + FE/BE total mismatch |

---

## Recommendations

1. Fix money preview trust (blocks UX confidence).  
2. Explicit access-denied UX.  
3. Counter-mode defaults: walk-in + barcode focus + large pay button.  
4. Confirm dialogs for Cancel / Complete with stock impact summary.  
5. Hindi i18n when expanding beyond metro pilots (plan notes English-first).
