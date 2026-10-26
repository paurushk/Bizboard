# Bizboard demo script (BB-134)

A 20-minute walk-through for a trader (owner, booker or munshi) with their CA optional. It shows
the daily loop first and leaves setup for last, because that is what they will judge us on.

## Before the call

1. A local or demo environment (never production):
   ```bash
   python manage.py seed_demo --with-activity
   ```
   This creates **Demo Traders** (Bengaluru, regular GST) with three customers (local B2B,
   inter-state B2B, walk-in), three items with opening stock, 24 invoices over the last three
   months, receipts that leave bills paid, part-paid and unpaid, and one return. Re-running adds
   nothing. Sign in as `demo@bizboard.local` with the seed password (in the command output).
2. Open the app once to warm it up, set the browser to 100% zoom, close other tabs.
3. Have a phone ready to show the same screens on mobile and the Hindi switch.
4. Know their old software (Tally / Busy / Vyapar / Marg / Excel) and trade before the call.

## The script

| Min | Show | Say (in their words) | Point to |
|---|---|---|---|
| 0–2 | **Dashboard** | "This is your business this morning: what you sold, what is due to you, what needs attention." | Sales trend, Receivables, Needs attention |
| 2–6 | **New sales invoice** for Sharma Medicals: scan or search an item, change quantity, see GST split | "A GST bill in under a minute. CGST/SGST or IGST is decided from the customer's state." | Totals preview; Complete; PDF; WhatsApp share link |
| 6–8 | Same bill for **Patel Pharma (Maharashtra)** | "Inter-state, so IGST; nothing to choose." | IGST line |
| 8–10 | **Receipts**: take part payment against two bills | "Partial payments are allocated bill by bill; TDS can be recorded too." | Allocation, balance left |
| 10–12 | **Outstanding / aging** | "Who owes what, how old, and a reminder message ready to send." | Aging buckets, reminder |
| 12–14 | **Stock** for Paracetamol | "Stock went down with every bill; the return put one strip back." | Stock ledger, return line |
| 14–16 | **GSTR-1 worksheet** for last month | "Your CA files from this. B2B, B2C, HSN summary, Excel download." | Worksheet; not auto-filing |
| 16–18 | Phone: same invoice, **Hindi** switch | "Your staff can work in Hindi on a phone." | Mobile layout, language switch |
| 18–20 | **Bringing their data** | "We import your parties and items from {their software}, then run one month in parallel so your CA can compare trial balances." | Settings → Import; `docs/pilot/RECRUITMENT.md` §6 |

## Questions they will ask

| Question | Honest answer |
|---|---|
| Does it file GST for me? | No. It prepares GSTR-1/3B worksheets; your CA files on the portal (`/limits` in the app). |
| e-invoice / e-way bill? | Not generated in this release; record the IRN/e-way number from your current tool. |
| Is my data safe / private? | Separate per company (row-level security), two-step sign-in for owners and accountants, full Excel export any time, support sees data only if you allow it for one request. |
| Can I leave? | Yes: Settings → Backup / Export gives every record as Excel/CSV plus invoice PDFs. |
| Offline? | POS drafts work offline on the device and sync later; full books need the internet. |
| Price? | From the signed price sheet (`docs/roadmap/SIGNOFF_PACK_2026-10-23.md`, item B-1); do not quote unsigned numbers. |

## Leave behind

- The in-app **Help** centre (250+ answers, searchable in English and Hinglish).
- The **Getting started** list on their dashboard after sign-up.
- The pilot one-pager: `docs/pilot/RECRUITMENT.md` §3 (outreach) and §6 (import and parallel month).

## Do not

- Demo on production or with a real customer's data.
- Promise anything listed on the in-app **What this pilot does not do** page.
- Quote prices, trial length or SLAs that are not signed.
