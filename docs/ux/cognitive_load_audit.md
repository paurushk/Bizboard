# Cognitive load audit

Date 2026-09-30. Method: static count of controls per page (following first-degree local imports), plus the crawl's count of visible inputs. Scores are **triage heuristics**, not measured workload. They rank where to look first and where NASA-TLX-lite sessions should go. Data: `docs/ux/static_scan.csv`; ledger columns `choice_count` and `cog_load_1to5` in `L1_surface_ledger.csv`.

Score bands (weighted controls: fields 1.0, buttons 0.6, tabs 1.5, dialogs 1.0, steps 1.0): 1 = under 8, 2 = under 18, 3 = under 32, 4 = under 55, 5 = 55 or more.

Distribution over 154 unique page components: score 1: 76, 2: 42, 3: 22, 4: 9, 5: 5. **Most screens are light. The problem is concentrated.**

## Score 5 and 4 screens

| Screen | Path | Choices | Fields | Buttons | Tabs | Dialogs | Hard-coded strings | Score |
|---|---|---|---|---|---|---|---|---|
| Products | /inventory/products | 121 | 59 | 58 | 4 | 5 | 46 | 5 |
| New invoice | /sales/new | 120 | 49 | 68 | 3 | 7 | 20 | 5 |
| New purchase | /purchases/new | 102 | 42 | 60 | 0 | 7 | 17 | 5 |
| Item dialog | (opens from Products) | 101 | 52 | 45 | 4 | 4 | 45 | 5 |
| Invoice detail | /sales/history/:id | 82 | 27 | 55 | 0 | 5 | 31 | 5 |
| POS | /pos | 59 | 22 | 36 | 1 | 7 | 1 | 4 |
| Leads | /crm/leads | 55 | 21 | 34 | 0 | 4 | 0 | 4 |
| GST settings | /settings/gst | 54 | 26 | 28 | 0 | 3 | 19 | 4 |
| Users settings | /settings/users | 50 | 30 | 20 | 0 | 2 | 16 | 4 |
| Customer ledger | /reports/customer-ledger | 46 | 21 | 21 | 4 | 0 | 1 | 4 |
| Sales history | /sales/history | 43 | 12 | 31 | 0 | 3 | 0 | 4 |
| Quotations | /sales/quotations | 43 | 19 | 24 | 0 | 2 | 0 | 4 |

Visible inputs at first paint (crawl): New purchase 28, New invoice 23, GST settings 21, Company settings 18, Item settings 14, New sales order 14. The median page has 1.

## Types of load found

| Type (Sweller) | Where | Example | Fix direction |
|---|---|---|---|
| Extraneous | New invoice header | Godown, Cost centre, SEZ/RCM, e-commerce GSTIN, Price mode visible for a plain cash sale | Progressive disclosure with a one-line summary of non-defaults (A2-5) |
| Extraneous | Invoice bottom | Three completion buttons plus five shortcut hints | One primary action (A4-1) |
| Extraneous | Receipts | Empty Source and UTR columns | Hide empty columns (A4-2) |
| Extraneous (language) | Collections, error card | "This list is a screen. It is not a prediction model." | Owner-language copy (A3-5, A3-1) |
| Intrinsic (irreducible) | GST fields, TCS, place of supply | Tax rules | Defaults from company settings and customer; explain, do not hide |
| Germane (worth adding) | First-run and empty states | Guided next step | Actionable blocked-state (A2-8) |

## Laws applied

| Law | Finding |
|---|---|
| Hick | Invoice completion offers three actions; Products offers 58 buttons. Group, rank or search |
| Miller / chunking | New invoice header is one flat group of about 10 fields. Chunk into Party, Document, Tax |
| Fitts and thumb zone | 10 targets per page under 44px at phone width; 30 or more on editors. POS tender already has 48px below sm (partial L7) |
| Recognition over recall | Non-default options hidden behind menus need a visible summary so users do not have to remember them |
| Error slip vs mistake | Slips (wrong quantity, wrong customer) covered by draft, hold and credit hold; mistakes (wrong tax setting) are not surfaced early enough because options are hidden |

## What to test with users (Phase 1 step 6, not yet done)

Time and NASA-TLX-lite on T2, T4, T5, T8 (see `heart_metrics.md`), on the current New invoice versus the progressive-disclosure design before building it fully.
