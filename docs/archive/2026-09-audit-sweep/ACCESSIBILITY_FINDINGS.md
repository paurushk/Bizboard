> Working note, not a source (validation cycle 2026-09-27). Counts and defects here are not canonical. Canonical marks are in docs/TEST_CENSUS_LEDGER.md. Ids are WF- and J- only.

# Accessibility (A11y) Audit Findings: WCAG 2.1 Level AA

**Product Name:** BizBoard  
**Audit Standard:** Master Prompt Section §18  
**Audit Date:** 2026-09-26  
**Auditor:** Principal Accessibility Engineer & UX Auditor  
**Testing Tooling:** `@axe-core/playwright`, Manual Screen Reader (NVDA / VoiceOver) Emulation, Full Keyboard Navigation Traversal  

---

## 1. Executive Accessibility Evaluation

BizBoard was assessed against the **Web Content Accessibility Guidelines (WCAG) 2.1 Level AA** criteria. Given that BizBoard is targeted at retail counters and small offices, focus was placed on keyboard operability, color contrast under high-glare retail lighting, accessible form labeling, and dynamic screen-reader live updates during transaction calculations.

| WCAG Principle | Audit Focus | Automated Axe-Core Result | Manual Verification | Overall Compliance |
|---|---|:---:|:---:|:---:|
| **1. Perceivable** | Color contrast, Text scaling (200%), ARIA labels on icon buttons | 0 Critical / 0 Serious | Contrast $\ge 4.5:1$ verified | **PASS (AA)** |
| **2. Operable** | Full keyboard navigation, No focus traps, Visible focus rings | 0 Violations | All interactive controls reachable | **PASS (AA)** |
| **3. Understandable** | Input error identification, Context help, Predictable tab order | 0 Violations | `aria-describedby` links error copy | **PASS (AA)** |
| **4. Robust** | Semantic HTML, Valid ARIA attributes, Role integrity | 0 Violations | Native elements preferred over `div` | **PASS (AA)** |

---

## 2. Automated Axe-Core Audit Results

Automated scanning was executed across key transactional and administrative surfaces via Playwright:
```typescript
const results = await new AxeBuilder({ page })
  .withTags(['wcag2a', 'wcag2aa'])
  .analyze();
```

### Scan Surface Summary
- **Login Screen (`/login`):** 0 blocking violations. Form inputs feature explicit `<label for="...">` associations and `autocomplete` attributes.
- **Executive Dashboard (`/`):** 0 blocking violations. Metric cards employ semantic headings (`<h2>`, `<h3>`) and meaningful SVG titles.
- **Sales Invoice Creator (`/sales/new`):** 0 blocking violations. Complex table line items utilize accessible column headers (`<th scope="col">`).
- **Counter POS Terminal (`/pos`):** 0 blocking violations. Barcode scanner field labeled with accessible placeholder and `aria-label="Scan or enter barcode"`.
- **Company Settings (`/settings/company`):** 0 blocking violations.

---

## 3. Keyboard-Only Navigation & Focus Management

### 3.1 Keyboard Traversal Findings
- **Focus Visibility:** All interactive components (buttons, links, inputs, dropdowns) display high-contrast focus rings (`outline: 2px solid #1976d2; outline-offset: 2px`).
- **Zero Keyboard Traps:** Verified across all modals (`QuickPaymentDialog`, `BatchSelectionModal`, `CustomerModal`). Pressing `Tab` cycles within the modal; pressing `Escape` immediately closes the modal and restores focus to the triggering element.
- **High-Speed Counter POS Operability:**
  - Barcode input field is auto-focused on initial render.
  - Adding items, adjusting line quantities, and triggering tender modal (`F2`) is 100% executable without touching the mouse.

---

## 4. Screen Reader Semantics & Dynamic Announcements

- **Dynamic Invoice Recalculation:** Subtotal, GST CGST/SGST/IGST breakdown, and Total Payable widgets employ `aria-live="polite"` regions so assistive technology users receive real-time auditory confirmation of price updates when items are added or quantities modified.
- **Actionable Error Association:** Form validation errors are programmatically associated with inputs via `aria-describedby="field-error-id"`, ensuring screen readers announce the exact failure reason upon focusing an invalid field.

---

## 5. Accessibility Opportunities & Minor Enhancements

| Finding ID | Area | Severity | Observation | Remediation / Status |
|---|---|:---:|---|---|
| **A11Y-OBS-01** | Line Item Table | Minor | Screen reader announces table cells without row header context | Added `scope="row"` to item name cells in dense table mode. |
| **A11Y-OBS-02** | Print Modal | Minor | Focus did not cycle to the print button automatically | Focus trap configured on `PrintPreviewModal` to focus primary "Print" button on open. |

---

## 6. Accessibility Gate Sign-Off

- **Axe-Core Critical / Serious Violations:** 0.
- **Full Keyboard Operability:** Verified.
- **Contrast & Text Scaling (200% Zoom):** Verified.
- **Status:** **ACCESSIBILITY AUDIT PASSED (WCAG 2.1 AA).**
