# Owner transfer and owner recovery (WP-ID1)

Code: `accounts/ownership.py`. A company always keeps at least one active Owner: role changes and
removals that would leave none are refused.

## Owner hands the company to someone else (self-serve)

Settings → Users → **Make owner**. The owner re-enters their password (and two-step code), picks an
active member and what their own access becomes (Manager, or leave). The member gets an email and
accepts in the app within 72 hours. Both are emailed when it's done. Any owner can cancel a pending
transfer.

API: `POST /api/v1/company/ownership/transfer/`, `/accept/`, `/cancel/`; `GET /ownership/`.

## Nobody can sign in as owner (staff-assisted recovery)

For: the owner left, lost their phone and recovery codes, or died, and the business still runs.

1. **Ticket.** The request must be a platform support ticket from someone at the business
   (Support → Platform tickets).
2. **Proof.** Ask for one of: an email sent from the address on the company's GST registration
   (check it on the GST portal search), or a letter on letterhead signed by a director/partner with
   a copy of their PAN. Note exactly what you checked. Do not accept a phone call alone.
3. **Request** (staff member 1):

   ```
   python manage.py owner_recovery request --company <id> --staff <you> --ticket <id> \
       --email <proven address> --proof "<what you checked>" --reason "<why>"
   ```

4. **Approve** (staff member 2, a different person): Django admin → Ownership transfers → select →
   *Approve recovery*. Every current owner is emailed and has **72 hours** to cancel.
5. After 72 hours `support.tasks.complete_owner_recoveries_task` (hourly) sends a normal owner invite
   to the proven address. The new owner sets their own password, then two-step verification. If the
   proven address is already an active member, they are made owner in place (no invite; their
   access is never switched off). An approved recovery must complete within 7 days of the wait
   ending, and an unapproved request lapses after 14 days: start again with fresh proof.
   **Lost phone and recovery codes:** if the owner being recovered still has two-step on, reset it
   as part of the same approved recovery (`python manage.py reset_user_mfa --email <address>`),
   noting it on the ticket; otherwise the invite or sign-in asks for the lost code again.
6. Reply on the ticket. Old owners keep their access unless the business asks you to remove them
   (do that only with a second written request).

Every step writes an audit row. If an owner cancels during the wait, stop and talk to them.
