# Reporting a security problem

Published at `/.well-known/security.txt` (WP-SC1). Before launch: set the real security inbox in
`web/public/.well-known/security.txt` and here, and have counsel approve the safe-harbour
paragraph.

## How to report

Email the security inbox named in `/.well-known/security.txt` with:

- what you found and where (URL, API path, app screen);
- steps to reproduce, and what an attacker could do with it;
- your name or handle if you want credit.

Please don't include real customer data in the report. If you came across some, tell us what kind
it was, not the data itself.

## What we do

| Step | Target |
|---|---|
| Acknowledge your report | 2 business days |
| First assessment (valid or not, severity) | 5 business days |
| Fix for a Critical or High issue | 30 days, sooner where we can |
| Tell you it's fixed | when the fix is live |

## In scope

The Bizboard web app, its API (`/api/`), the Android app, and public invoice, quotation, receipt
and payment links.

## Out of scope

- Denial of service and load testing.
- Social engineering of staff or customers, and physical attacks.
- Reports from automated scanners with no shown impact.
- Missing best-practice headers with no exploit.
- Third-party services we use (report those to the vendor).

## Testing rules

- Use only accounts you created yourself. Don't access, change or delete other people's data.
- Stop and report as soon as you can see data that isn't yours.
- Don't publish the issue until we've fixed it or 90 days have passed, whichever comes first.

## Safe harbour

**[For counsel to draft and approve.]** Intended meaning: if you follow these rules in good faith,
we won't take legal action against you for your research.
