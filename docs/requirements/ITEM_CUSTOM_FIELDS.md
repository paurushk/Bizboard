# Item custom fields (v1)

**Status:** Implemented (v1 complete) — 28 Aug 2026
**Date:** 27 Aug 2026 · **Rev 2** — stock screens, POS, and a column picker are now fully in scope; adds the engineering build plan, phased delivery, and test plan.
**Depends on:** existing `Company.item_custom_field_defs`, `Product.custom_fields`, Create Item Custom tab, products import.

**Lifecycle:** Define → Capture → Import → Store → Display → Search → Filter → Edit → Change safely.

This document is the implementation plan. It supersedes the earlier chat FR and the "defaults are injected when the list is empty" behaviour in code.

---

## 0. Decisions locked

| Topic | Decision |
|---|---|
| Inactive storage | One list; each row has `active: true\|false`. Array stored as `[active in display order …, inactive …]`. Inactive rows are omitted from every product surface. |
| Empty company list | **No custom fields.** Stop injecting Brand code / form / sub brand form. |
| Zero active fields | Allowed. Custom tab empty state; no extra list columns; no custom filter bar. |
| Import match | Normalized **active key** or normalized **current label** only. Delete `CUSTOM_FIELD_HEADER_KEYS`. No generic alias dictionary. |
| Inactive Brand Code | Unmatched extra column → ignored (existing import behaviour). Not an error. |
| Search | ORM `Q(custom_fields__<key>__icontains=q)` per **active** key. Same path on Postgres and SQLite JSON1. Never `custom_fields__icontains` on the whole blob. |
| Filter API | `?cf.<key>=<value>` repeatable. OR within a key, AND across keys. **Active List keys only** on list pages; text fields are search-only in v1. |
| List columns | Whatever is **active** — no "defaults vs added" split. |
| Column picker | New shared control on **Items** and **Current stock**. Visibility only (no per-user column reorder in v1). Persist per user × company in browser `localStorage`; no user-prefs API. |
| Key edit | Editable until first company Save of that key; then locked. Auto-suggest key from label (slug → camelCase) while new. |
| Type edit | Immutable after first save (same rule as key). Changing type would reinterpret stored strings. |
| Reorder | Up/down buttons. Do **not** add `dnd-kit` / `react-beautiful-dnd` (not in the web app today). |
| Caps | **20 active** definitions. **50 options** per List field. Inactive rows do not count toward 20. |
| Import vs later def edits | Freeze snapshot at preview; commit uses that map. Prefer commit-on-snapshot over failing a reviewed job. |
| Who edits definitions | `canManageUsers` (owner/admin). Item **values** stay with whoever can edit items. |
| Wire format | Omit empty keys. `customFields: {}` when none. Write: `""` or omit both clear the key. |
| Field types | **Text** and **List** (single-select). Number, date, multi-select, formula are out. |
| Stock surfaces | Custom fields are read-only **item identity** on stock screens. Nothing is stored on `StockBalance` / `StockMovement` / adjustment / count / transfer lines. |
| POS surfaces | Same product search (values included) + optional List filter on the finder. Nothing on cart line or receipt. |
| In v1 | Items list + column picker + List filters + value search; **Current stock** columns/filters/search; **POS** finder search/filter; List filter bar on sales / purchase / stock product pickers. |
| Out of v1 | Invoice/PDF, GST, reports, e-invoice, generic aliases, number/date/multi-select/formula, user-prefs API, GIN index unless proven. |

**List stays in v1.** It is what makes filter/drill-down usable. Free-text alone cannot be filtered cleanly.

---

## 0b. Why this feature (competitive rationale)

Competitor catalogues (pharma-distribution ERPs, Vyapar-class billing apps) let a shop attach extra item attributes — Brand code, Brand form, drug licence, rack, old-system code — and, crucially, **find and group items by them** while billing. Bizboard already stores `Product.custom_fields` but the data is write-only: no list columns, no search, no filter, and a hardcoded Brand-only importer.

v1 reaches parity on the basics (define → capture → import → show → search → filter across catalogue, stock, and POS) and **beats the field on schema-change safety**: immutable keys, retain-on-remove, no key reuse, and imports that never silently re-map columns. Most SME tools store additional fields positionally and corrupt historical rows when a field is renamed, reordered, or removed. "Rename or remove an attribute and your old data stays correct" is the differentiator.

Deliberately **not** in v1: printing custom fields on invoices, custom reports, typed number/date fields. Those are the next lever, not this release.

---

## 1. Goal

Custom fields must not be write-only. A shop defines them in Item Settings, fills them on Create Item and bulk upload, then **sees, searches, and filters** them on catalog, stock, and POS find.

They must not change stock math, GST, HSN, unit, or price.

---

## 2. Definition model

Company setting `item_custom_field_defs` is an ordered JSON array.

```json
[
  {
    "key": "brandForm",
    "label": "Brand form",
    "type": "list",
    "active": true,
    "options": ["Strip", "Bottle", "Tube"]
  },
  {
    "key": "color",
    "label": "Color",
    "type": "text",
    "active": true
  },
  {
    "key": "oldRef",
    "label": "Old reference",
    "type": "text",
    "active": false
  }
]
```

- **key:** stable identifier. Letters and digits; camelCase allowed. No spaces. Max 64. Immutable after the definition is first saved on the company. Case-insensitive unique per company across all rows.
- **label:** user-facing. Trimmed. Max 80.
- **type:** `text` | `list`. Immutable after first save (same rule as key).
- **active:** hidden from all product surfaces when `false`; values retained on items.
- **options:** required for `list`, ignored for `text`. Unique among the field's options (case-insensitive after trim). Max 50. Empty options array is invalid for an active List field.

### Validation

- Key required; case-insensitive unique per company among **all** rows (active and inactive).
- Key must not collide (normalized) with a reserved item field/alias — see §8.1 `RESERVED_ITEM_KEYS`.
- Label required; unique among **active** rows, case-insensitive after trim; not a reserved column header.
- Max **20 active** rows. Max **50 options** per List field.
- Saved key and type cannot be changed. New unsaved rows: key editable; suggest camelCase from label; user can still edit before Save.
- A key present in the stored array may not disappear from an incoming array — "remove" is `active: false`, not deletion.
- Reactivate = set `active: true` and move the row to the **end of the active section** (display order of remaining actives unchanged).
- A new key must not case-insensitively match any previously saved key (reuse rejected).

### Item Settings UI

- Owner/admin only (`canManageUsers`).
- Add field, label, type, List options, up/down (active rows only), remove (→ inactive + confirmation).
- May remove the last active field (zero active is valid).
- Confirmation copy, e.g. *Remove "Batch Reference"? Existing item values will no longer be visible but will not be deleted.*
- Removed key **cannot** be used on a new field.
- Inactive rows shown in a collapsed "Removed fields" section with a **Restore** action; keys not reusable.
- Client-side mirror of the validation above with inline errors; the server remains the source of truth (surface 400s).

---

## 3. Capture

### Create / Edit Item

- Custom tab: one control per **active** definition, in active order, using current labels.
- Text → text input. List → single-select of current options.
- Zero active → empty state (no inputs), not the three brand fields.
- Blank / cleared select → no value (key omitted on save).
- List: stored value must be one of the current options **or** a previously stored orphan (option later removed). Orphans remain visible on edit (select shows the stored string) so data is not silently dropped. Import of a non-option value fails that row.
- On save the form submits only **active** keys. The API merges (see §4) so retained inactive values survive every resave.

### Bulk upload (products)

Normalization for match: trim; case-insensitive; collapse internal whitespace; treat `_`, `-`, and space as the same.

A column maps to a field when the normalized header equals the normalized **key** or normalized **current label** of an **active** definition at preview time.

- No `CUSTOM_FIELD_HEADER_KEYS`. `brandCode` / `brandcode` match key; `brand_code` / `Brand Code` match label "Brand code" **only if that field is active**.
- Two columns → same field: validation error; do not commit.
- Blank cell → no value.
- List column: non-blank cell must match an option (normalized); else row error.
- Unmatched extra columns: existing import behaviour (do not fail the job only for that).
- **Snapshot:** on preview, persist on `ImportJob`:
  - `custom_field_defs_snapshot` — active defs used for matching
  - `custom_field_header_map` — `{ "Brand Code": "brandCode", ... }`
- **Commit** uses that map only. Do not re-resolve against live defs. If a mapped key no longer exists on the company at all (should not happen; keys are immutable), fail clearly.
- Update-existing-item commit **merges**: only columns present in the map are written; other stored keys (including inactive) are left untouched.
- **Template:** the products template (CSV + xlsx `items` sheet) drops the hardcoded `brand_code` / `brand_form` / `sub_brand_form` columns and appends one column per active custom field, headed by its **label**.

---

## 4. Storage and API

### Product

- `custom_fields`: JSON object, keys → strings.
- Canonical read: omit empty keys; `{}` if none.
- Write: omit or `""` deletes that key; other keys unchanged. Final stored dict = `{…retained keys already on the item that are NOT active defs, …validated incoming values for active defs}`.
- Unknown key on write (not an active def and not already stored on the item) → `400`.
- List value not in the field's current options (and not already stored on the item) → `400`.

### Company

- Return the full defs array (including inactive) to Item Settings.
- Product UI, list, stock, POS, import matching use **active only**.

### Search (products API + stock API)

- Existing `q` / `search` still matches name, SKU, barcode, HSN.
- **Plus** per active key: `custom_fields__<key>__icontains=q` (ORM, OR-combined). Fallback if a Django/SQLite key-transform misbehaves: `KeyTextTransform` + `Cast` to `TextField` + `icontains` — still ORM, both DBs.
- Do not search keys or labels.
- Same search path POS already uses (`searchProducts` / list `q`).
- Stock list gains a `q` param that runs the same match via `product__…`.
- Table scan is acceptable at pilot volume; GIN/expression index only if `EXPLAIN` later requires it.

### Filter (products API + stock API)

- `?cf.<key>=<value>` — repeatable. **OR within a key, AND across keys.**
- Products: `Q(custom_fields__<key>__iexact=value)` per value.
- Stock: `Q(product__custom_fields__<key>__iexact=value)`.
- Honoured for **active List keys only**. Unknown / inactive / text keys are ignored — never build a JSON path from an unvalidated key.
- List pages persist the active filter in the URL query string (shareable drill-down).

---

## 5. Utilization

### 5.1 Items list

- **Column picker (new).** There is no picker in the app today; v1 adds one on Items.
- Toggleable columns: existing core columns (name, SKU, unit, price, GST, stock, tracking, status) **and** every **active** custom field.
- Default: core columns on; **all active custom columns on**. A company with `[]` has no extra columns. A seeded pharma company sees its three fields until the user hides them.
- Persistence: per user × company in **browser `localStorage`** (`bb:cols:<companyId>:<userId>:items`). Missing / corrupt / unreadable prefs → defaults above.
- Horizontal scroll must remain usable at 20 custom columns (existing `TableContainer` overflow).
- **List-type filter bar:** one filter control per **active List** field (All + each option). Text fields are not faceted; they are search-only.
- Empty custom values render blank.
- **Export:** the items export includes the currently visible custom columns and respects the active filter. (If no export exists today, a client-side CSV of the current result set is acceptable for v1 — see open decision.)

### 5.2 Current stock

Custom fields do not change quantities, lots, or godowns. They are **item identity** on the stock screen.

- `StockBalanceSerializer` exposes read-only `customFields` (`source="product.custom_fields"`) so the list renders columns without a second query.
- After product name / SKU: optional columns for active custom fields (same column-picker pattern; prefs key `bb:cols:<companyId>:<userId>:stock`, distinct from Items).
- List filters (same `?cf.` semantics as Items) so a shop can see on-hand for one Brand form.
- A stock search box (add one if the page has none) uses the **same products search**, so a custom value finds the item here too.
- Other stock workflows (adjustment, transfer, count, low stock) **do not** get extra table columns. Their **product pickers** get the shared List filter bar and hit the same products search API.

### 5.3 POS

- Scan / search / autocomplete uses the same products search → custom **values** find the item (barcode still exact-match first as today).
- The finder autocomplete secondary line may show up to two filled custom values so the cashier can tell similar SKUs apart. Cart line stays name + SKU + qty/price.
- Optional List filter bar on the POS finder (same options as Items). Not on the cart or receipt.
- Thermal receipt / GST invoice: **out of v1** (no custom fields on print).

---

## 6. Changing definitions after data exists

| Change | Behaviour |
|---|---|
| Rename label | Values stay on the key. All current surfaces use the new label. |
| Reorder active | Up/down. Create/Edit, Items, stock columns, POS filter order follow. |
| Add field | New empty input/column. Existing items have no value. Active count ≤ 20. |
| Remove field | `active: false`; confirmation; hidden everywhere; values kept. |
| Reuse removed key | Rejected. |
| Change key or type | Not after first save. |
| List: add option | Appears in selects, import, filters. |
| List: remove option | Stored item values that used it are **kept** (orphan). Edit still shows them. New import of that string fails. Filter "that option" no longer listed; search still finds the orphan via value `icontains`. |
| Reactivate | `active: true`; row moves to end of active section. |

---

## 7. Migration

1. **Stop injecting defaults** when `item_custom_field_defs` is empty (`[]` means none). Frontend must not seed Brand fields on an empty company response. Remove `DEFAULT_ITEM_CUSTOM_FIELD_DEFS` fallbacks in `ItemSettingsPage` and `ItemFormDialog`.
2. **Data migration (one-off, `accounts`):**
   - For each company, if `item_custom_field_defs` already has any of `brandCode` / `brandForm` / `subBrandForm`, **or** any product `custom_fields` contains one of those keys: ensure those three defs exist as `{ type: "text", active: true, ... }` (keep existing labels if present; default labels Brand code / Brand form / Sub brand form). Preserve any other defs the company already saved. Normalize every row to the full shape (`type`, `active`).
   - Everyone else: set `item_custom_field_defs` to `[]` if null; do **not** insert the three keys. Those keys remain free.
3. Existing `custom_fields` JSON on products is unchanged.
4. Import: remove `CUSTOM_FIELD_HEADER_KEYS`; matching is active key/label only after this migration (pharma tenants still have active Brand defs).
5. New `ImportJob` fields (`custom_field_defs_snapshot`, `custom_field_header_map`) are additive, default empty.

Those three keys are **not** globally reserved.

---

## 8. Engineering implementation plan

### 8.1 Shared backend module — `backend/masters/custom_fields.py` (new)

Single home for logic imported by `accounts`, `masters`, and `imports`.

```python
normalize_header(s) -> str          # trim → lower → collapse [_\-\s]+ → " " → strip
RESERVED_ITEM_KEYS: frozenset       # PRODUCTS_ITEM_COLUMNS + {id,status,created_at,updated_at,
                                    #   brand,category_name,hsn,quantity} + MASTER_COLUMN_ALIASES values
MAX_ACTIVE_FIELDS = 20
MAX_OPTIONS = 50

validate_definitions(existing: list, incoming: list) -> list
    # raises rest_framework ValidationError. Enforces, in order:
    #  key format [A-Za-z][A-Za-z0-9]* / ≤64 / not reserved (normalized)
    #  no existing key removed from incoming (remove == active:false)
    #  key ci-unique within incoming; new key must not ci-collide with any existing key
    #  label ≤80 / not reserved / ci-unique among active (trim + ws-collapse)
    #  type in {text,list}; immutable vs existing row of same key
    #  list => options non-empty, ≤50, each ≤80, ci-unique; text => no options
    #  ≤20 active
    #  returns [active in display order …, inactive …]

active_defs(company) -> list                    # [d for d in defs if d["active"]]
resolve_import_columns(headers, defs) -> tuple[dict[str,str], list[str]]
    # ({header: key}, [error strings]); duplicate target key => error
build_search_q(term, defs, prefix="") -> Q      # OR of {prefix}custom_fields__{key}__icontains
apply_cf_filters(qs, query_params, defs, prefix="") -> qs
    # parses cf.<key>; OR within key (iexact), AND across keys; active List keys only
coerce_values(raw, defs, existing) -> dict
    # trim, drop blanks, list-option validation, merge retained inactive keys
```

Spike (P1, ~30 min): confirm `custom_fields__<key>__icontains` behaves on the installed Django + the SQLite JSON1 test wheels; adopt the `KeyTextTransform` + `Cast(TextField)` form if not.

### 8.2 Backend changes by file

| File | Change |
|---|---|
| `backend/masters/custom_fields.py` | **New** module above. |
| `backend/accounts/serializers.py` | Replace `_item_custom_field_defs` with `validate_definitions(self.instance stored defs, value)` in `CompanySerializer` and `CompanySettingsSerializer`. **Delete the DEFAULT fallback branch.** Keep returning the full array (incl. inactive) on read. |
| `backend/masters/serializers.py` | `ProductSerializer.validate_custom_fields` → `coerce_values(...)`. `custom_fields` already in `fields`. |
| `backend/masters/views.py` | `ProductViewSet.get_queryset`: load `active_defs(company)` once; extend the `q` OR-block with `build_search_q`; apply `apply_cf_filters`. |
| `backend/inventory/views.py` | `StockBalanceViewSet.get_queryset`: add `q` (product name/SKU/HSN + `build_search_q(..., prefix="product__")`) and `apply_cf_filters(..., prefix="product__")`. |
| `backend/inventory/serializers.py` | `StockBalanceSerializer`: add `custom_fields = JSONField(source="product.custom_fields", read_only=True)`. `select_related("product")` already present. |
| `backend/imports/services.py` | Delete `CUSTOM_FIELD_HEADER_KEYS` + `_custom_fields_from_row`. In validate/preview: `resolve_import_columns`, duplicate-column job error, List-option row validation, persist snapshot + header map. In `commit`: apply frozen map verbatim, merge on update, fail only if a mapped key is entirely gone. `products_template_csv` / xlsx builder: thread `company`, drop `brand_*` literals, append active labels. |
| `backend/imports/models.py` | `ImportJob`: `custom_field_defs_snapshot = JSONField(default=list, blank=True)`, `custom_field_header_map = JSONField(default=dict, blank=True)`. |

### 8.3 Frontend changes by file

| File | Change |
|---|---|
| `web/src/types/domain.ts` | `ItemCustomFieldDef = { key; label; type:'text'\|'list'; options?: string[]; active: boolean }`. Add `StockBalance.customFields?: Record<string,string>`. |
| `web/src/pages/inventory/itemCustomFieldDefaults.ts` | Keep the type export; delete `DEFAULT_ITEM_CUSTOM_FIELD_DEFS` (or `= []`). |
| `web/src/pages/settings/ItemSettingsPage.tsx` | Rewrite: key (locked once server-known; slug-suggest while new), label, type select, options editor for List, up/down on active rows, Remove → confirm dialog → `active:false`, collapsed "Removed fields" + Restore. Client validation mirror. |
| `web/src/pages/inventory/ItemFormDialog.tsx` | Custom tab: List → `TextField select` (+ orphan value as selectable entry); Text → text field; zero active → hide tab. Submit only active keys. Keep `?? custom[def.label]` legacy read one release. |
| `web/src/pages/inventory/ProductsPage.tsx` | Render visible custom columns; mount `ColumnPicker` (`tableId:"items"`); mount `CustomFieldFilterBar`; `cf` state in `useSearchParams` → `listProductsPage({ cf })`; export includes visible custom columns. |
| `web/src/pages/inventory/CurrentStockPage.tsx` | Same `ColumnPicker` (`tableId:"stock"`) + `CustomFieldFilterBar`; add search box wired to products search; columns from `row.customFields`. |
| `web/src/pages/pos/PosPage.tsx` | `CustomFieldFilterBar` (compact) on the finder; `cf` into the product query; secondary autocomplete line shows up to two filled values. |
| `web/src/pages/sales/NewInvoicePage.tsx`, `web/src/pages/purchases/NewPurchasePage.tsx` | `CustomFieldFilterBar` popover by the product Autocomplete; `cf` into `product-picker` + `product-search` queryKey/queryFn. |
| `web/src/pages/inventory/StockAdjustmentPage.tsx`, `StockCountPage.tsx`, `StockTransferPage.tsx` | `CustomFieldFilterBar` on their product Autocompletes. |
| `web/src/api/legacy/masters.ts` | `listProducts` / `listProductsPage` accept `cf?: Record<string,string[]>`; serialize repeated `cf.<key>=v`. Update `filterProducts` mock to apply `cf`. |
| stock list API fn | accept `cf` + `q`. |
| `web/src/hooks/useProductSearch.ts` | optional `cf` arg → queryKey + queryFn. |
| `web/src/i18n/*` | filter labels, remove-confirmation copy, column-picker + settings strings. |

### 8.4 Frontend shared components (new)

- `web/src/components/ColumnPicker.tsx` + `web/src/hooks/useColumnPrefs.ts`
  - `useColumnPrefs(tableId, allColumns)` → `{ visibleIds, isVisible, toggle, reset }`; persists `{ hidden: string[] }` to `localStorage`; every read/write in `try/catch`; corrupt/absent → all visible.
  - `allColumns`: `{ id, label, group:'standard'|'custom', removable }`; custom columns `id:"cf:<key>"`, label = `def.label`, in definition order.
  - UI: **Columns** button → popover, checkboxes grouped Standard / Custom fields, **Reset**. Visibility only in v1.
- `web/src/components/CustomFieldFilterBar.tsx`
  - Props: active defs, current `Record<string,string[]>`, `onChange`.
  - One `Autocomplete multiple` (or `Select multiple`) per active **List** def; options = `def.options ∪ distinct values present`.
  - Collapses into a **Filters** popover when > 2 List defs.
  - Text defs are not rendered here in v1 (search-only) — leave a typed extension point.

### 8.5 Migrations

- `backend/accounts/migrations/00XX_custom_field_defs_shape.py` — data migration per §7.2.
- `backend/imports/migrations/00XX_importjob_cf_snapshot.py` — the two additive `ImportJob` JSON fields.
- No `masters` migration (`Product.custom_fields` already exists).

### 8.6 Feature flag

`feature_flags["item_custom_fields_v2"]` gates list custom columns, the column picker, every filter bar, and POS/stock filter. Default **ON**; a company JSON value of `false` is the kill switch. The backend accepts the new def shape and serves `customFields` regardless of the flag. Item Settings (define fields) stays available to `canManageUsers` even when the utilization flag is off, so defs can still be edited.

Capture (Create / Edit Item Custom tab) is not gated — values can still be written when columns/filters are hidden.

---

## 9. Phased delivery & estimates

| Phase | Scope | Size |
|---|---|---|
| **P1** | `masters/custom_fields.py`; definitions validation in both company serializers; `accounts` data migration; `ImportJob` snapshot fields; cross-DB search spike; unit tests. No visible change. | 2–3 d |
| **P2** | Item Settings rewrite — types, options, up/down, remove/restore, key/type lock, client validation. | 2–3 d |
| **P3** | `ItemFormDialog` List/Text inputs + empty state; `ProductSerializer` merge/validation end-to-end. | 1–2 d |
| **P4** | Backend search + `?cf.` filter for **Items and Stock**; `StockBalanceSerializer.customFields`; stock `q`. | 2 d |
| **P5** | `ColumnPicker` + `useColumnPrefs`; Items list custom columns + picker + export. | 2–3 d |
| **P6** | `CustomFieldFilterBar`; Items + Current Stock filter bars + URL persistence; Current Stock columns + search box. | 2–3 d |
| **P7** | Filter bar into pickers: invoice, purchase, POS, stock adjust / count / transfer; POS secondary line. | 2–3 d |
| **P8** | Def-driven import: column resolution, duplicate-column error, List validation, preview/commit snapshot, merge on update, template columns. | 3–4 d |
| **P9** | Remove FE default fallbacks; flag on pilot cohort; full E2E acceptance pass; doc + changelog. | 1–2 d |

**≈ 4–5 weeks**, one developer, including review. P1→P5 = "attributes visible and manageable everywhere"; P6→P7 = "filter and drill-down across Items / Stock / POS / transactions"; **P8 can run in parallel after P1**.

---

## 10. Test plan

### 10.1 Backend — `backend/tests/test_item_custom_fields.py` (new)

| Area | Cases |
|---|---|
| Definitions | key format / reserved / ≤64 / immutable / ci-unique incl. inactive; type immutable; reuse-removed-key rejected; label ci-unique among **active** only; List options non-empty / ≤50 / ≤80 / ci-unique; ≤20 active; deactivate keeps the row; **restore re-activates and values reappear**; existing key missing from payload → error. |
| Product serializer | write / trim / blank-drop; unknown key → 400; List value not in options → 400; orphan value already on item still accepted; **PATCH merges — a retained inactive value survives an unrelated resave**. |
| Items search / filter | value substring matches on `q`; searching a **key name** or **label text** does not match every item with that field; only active defs searched; `?cf.` — OR within key, AND across keys; List `iexact`; unknown / inactive / text key ignored. |
| Stock endpoint | `?cf.` via `product__`; `q` value search; serializer exposes `customFields`; `custom_fields` not writable through any stock endpoint. |
| Import | header matches key; header matches current label; two headers → one key ⇒ job `FAILED`, nothing committed; List cell not an option ⇒ row error; extra unrelated columns don't fail the job; **defs changed between preview and commit ⇒ commit uses the frozen map**; mapped key entirely gone ⇒ clear failure; update path merges retained keys; generated template contains the active labels and not `brand_*`. |
| Migration | company with legacy Brand defs or Brand values ⇒ three text defs seeded + other saved defs preserved; company without ⇒ `[]`, keys still free; every row normalized to full shape. |

### 10.2 Frontend

No web test harness exists under `web/src/**/*.test.*` today. If one is added:

- `useColumnPrefs`: persistence round-trip; corrupt / throwing `localStorage` → all visible, no crash.
- `ItemSettingsPage`: add / remove / restore; key locked after save; type locked; List options validation; last-row removal allowed.
- `ProductsPage` / `CurrentStockPage`: render only visible custom columns; filter change updates `cf` query params and refetches.
- `CustomFieldFilterBar`: emits `Record<string,string[]>` with OR-within-key semantics.
- POS / stock pickers: applied filter constrains options.

### 10.3 E2E (Playwright — extends the existing E2E master prompt)

The acceptance list in §11 plus:

- Filter the **sales** product picker by Brand form, add the item, save the invoice.
- Hide a custom column via the column picker; it stays hidden after reload.
- Filter **Current stock** by Brand code; on-hand totals reflect only matching items.
- Filter **POS** finder by Brand form; scan an unrelated barcode still resolves exact-match first.

---

## 11. Acceptance (v1)

1. New company: Item Settings empty; Create Item Custom tab empty; Items list has no custom columns; POS / stock search behaves as today for name / SKU / barcode.
2. Seeded / migrated company that already had Brand custom data: three **text** fields active; Items list shows them by default; import `Brand Code` maps to `brandCode`.
3. Define Text + List (≤ 20 active, List ≤ 50 options) → Create / Edit, Items (picker + List filters + columns), Current stock (columns / filters / search), POS finder all use them in definition order.
4. Search by a **value** finds the item on Items, POS, and stock product find. Search by the **label** does not match every item that has that field.
5. Import header = key or current label; duplicate mapped columns fail validation; List cell must match an option; commit uses the preview snapshot if defs change later.
6. Remove last field → confirm → zero active → no extra columns / filters; stored values retained; the same key cannot be added again; Restore brings the field and its values back.
7. Column picker can hide a custom column on Items and on Current stock; prefs survive reload (localStorage) and are independent per table.
8. Rename a label and reorder fields → every surface (Create / Edit, Items, stock columns, POS filter) follows the new label and order; stored values unchanged.
9. Invoice / PDF, GST, and stock **quantities** unchanged.

---

## 12. Decisions locked (v1)

These were open during planning; they are locked for this release.

| # | Question | Decision |
|---|---|---|
| 1 | Items-list **export** — build a client-side CSV now, or defer until a server export exists? | Built now (full filtered set). |
| 2 | Column picker on **which** stock lists — Current stock only, or also Low stock / Expiry alerts / Serials? | Current stock only. |
| 3 | Unknown custom key on API write — reject `400`, or silently drop? | Reject `400`. |
| 4 | Text-field **filtering** on list pages — v1 List-only faceting, or also a "contains" box per text field? | List-only; text stays search-only. |
| 5 | POS finder secondary line showing up to two custom values — in v1, or defer? | In v1. |
| 6 | Feature-flag name and pilot cohort. | `item_custom_fields_v2` (default on; company JSON `false` is the kill switch). |

---

## 13. Out of scope (v1)

Invoice / PDF, GST returns, reports, e-invoice, number / date / multi-select / formula types, generic alias dictionary, user-prefs API (use `localStorage` for the column picker), custom fields on any transaction or stock-movement line, GIN index unless proven needed.
