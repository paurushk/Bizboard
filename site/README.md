# Bizboard marketing site — DRAFT, not published

Static draft of the marketing home page and pricing page, made under founder decision **D-15**
(`docs/roadmap/DECISIONS_2026-10-24.md`): "Draft now with the proposed prices marked as draft;
do not publish" (BB-133).

| File | What |
|---|---|
| `index.html` | Home: positioning, who it is for, what it does, GST worksheets with your CA, Hindi + English, phone/offline note, FAQ, trial CTA |
| `pricing.html` | Plan cards, comparison table, GST note, trial — DRAFT banner and a "Draft — not final" tag on every price and limit |
| `hi/index.html` | Hindi home page (pricing links go to the English page) |
| `styles.css` | Shared styles: system fonts, mobile-first, no frameworks |

Plain HTML + CSS. No JavaScript, no external fonts, CDNs, analytics or trackers. Every page has
`<meta name="robots" content="noindex">`. Open `index.html` in a browser to view.

## Where the content comes from

- Prices and limits: `docs/roadmap/SIGNOFF_PACK_2026-10-23.md` §B-1 (same values as
  `backend/billing/management/commands/seed_plans.py`). **Proposals, not signed.**
- Trial (14 days, no card, one per business, read-only after, never deleted): sign-off pack §B-2.
- Positioning: sign-off pack §B-11. Audience: §B-12 and `docs/requirements/REQUIREMENTS_BASELINE.md` §1.
- Features: requirements baseline §2–§3 (release 1 only; off-by-default modules are not mentioned).
- Limitations stated on the site: baseline §5–§6 and `docs/FREEZE_SCOPE.md` §C (worksheets are not
  filing, e-invoice preview only, payments sandbox, WhatsApp is a share link, offline drafts plaintext).
- Status page path `/status/`: `docs/ops/STATUS_COMMS.md`.
- Hindi terms: `web/src/i18n/hi.ts` (इनवॉइस, स्टॉक, गोदाम, खरीद, आपूर्तिकर्ता, लेखांकन, परीक्षण शेष …).

No customer counts, testimonials, logos, awards, certifications or uptime promises — none exist.

## Must be decided before publishing

1. **Signed prices and limits** — founder signs §B-1 (and decides the pilot-offer option). Then
   remove the draft banner and tags.
2. **GST on the subscription** — CA confirms the 18% GST treatment of Bizboard's own invoices (BB-124).
3. ~~**GST worksheets per plan**~~ — decided (D-16, 2026-10-25): every plan includes GSTR-1/3B
   worksheets; the code and the pricing page now say so.
4. **How customers pay for a plan** — live gateway not switched on; pricing page says it will be confirmed.
5. **Domain** — replace every `[app domain]` (register link and status page). `href="https://[app domain]/register"` is a placeholder and does not work.
6. **Legal pages** — Terms and Privacy Policy (drafts in `docs/legal/drafts/` are not approved);
   cancellation/refund wording (§B-4, counsel). Footers say "coming soon".
7. **Contact and grievance officer details** (DPDP / IT Rules) — none added.
8. **Analytics** — decide whether to use any, and consent wording if so. None added.
9. **Hindi review** — a native speaker should check `hi/index.html`; add a Hindi pricing page if wanted.
10. **Hosting** — where the static site lives; remove `noindex` only at publication.
