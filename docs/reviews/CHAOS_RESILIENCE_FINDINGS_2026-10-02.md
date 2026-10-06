# Chaos resilience findings — 2 Oct 2026

Four defects were reproduced. Each one needs a code fix. The regression oracles are in `backend/tests/test_chaos_resilience.py` and are currently failing on these four tests.

Phase 0 (existing resilience suite) passed: 57 tests, 13 skipped. The offline POS flush suite passed: 9 tests in `web/src/offline/flushPosCheckout.test.ts`. The parallel invoice-number race was not run. It needs Postgres (`pytest -m postgres`).

## Issues to fix

### CH-05 — P1 — A parked payment is discarded after two failed replays

**What happened.** A payment webhook that crashes before posting leaves a pending `DeadLetterEvent` with `attempts=1` and does not mark the event seen. The reconcile sweep then calls `replay_dead_letter`. That function adds 1 to `attempts` in memory before `finalize_gateway_payment`. When finalize raises, the sweep adds 1 again and saves. One failed replay moved `attempts` from 1 to 3. The sweep discards at `attempts >= 5`, so the second failed replay discards the letter.

**Rows.** `DeadLetterEvent` `sandbox:pay_ch05` stayed `pending` with `attempts=3` after a single call to `_replay_pending_payment_dead_letters`. The Celery log recorded one `RuntimeError: still down`.

**Impact.** The gateway reconcile beat is the backup when the provider does not retry. Two beats (about 10 minutes at the current 5-minute schedule) drop that backup. The capture stays unposted until someone replays the letter by hand. The `attempts` value also overstates how many times posting was tried.

**Fix.** Count a failed replay once. `replay_dead_letter` should leave `attempts` unchanged until the outcome is known, and the sweep should be the only writer on the failure path. Discard on the fifth failed sweep, with the letter still `pending` and `attempts=5` before that call. Keep `finalize_gateway_payment` idempotent so a provider retry and a replay cannot create two receipts.

**Test.** `tests/test_chaos_resilience.py::test_ch_05_one_failed_replay_counts_as_one_attempt_and_five_discards`

### CH-07b — P2 — One PDF render error is final, and Celery reports success

**What happened.** `generate_invoice_pdf` is declared `autoretry_for=(Exception,), max_retries=3`. The render error is caught inside the task, `pdf_status` is set to `FAILED`, and the exception is not re-raised. Celery logged the task as succeeded in 14 ms with `retry_count=0`. `requeue_stale_invoice_pdfs` only requeues `QUEUED` rows older than 15 minutes, so a `FAILED` row is left alone. The same catch-and-mark-failed pattern is in `generate_credit_note_pdf`, `generate_debit_note_pdf`, and `generate_challan_pdf`.

**Rows.** Completed invoice `pdf_status` went from `QUEUED` to `FAILED` on the first `RuntimeError: font missing`. The sale itself stayed completed. No in-app owner notification was written.

**Impact.** A transient render failure (font, disk, a dropped connection) leaves the customer without a PDF. Recovery is the `regenerate-pdf` action, which an owner has to know to press. The sale, stock, and total are intact.

**Fix.** Let the exception propagate until Celery has used its three retries, and set `FAILED` only on the last attempt. Then send one in-app notification to the company owners. Apply the same rule to the credit note, debit note, and delivery challan tasks.

**Test.** `tests/test_chaos_resilience.py::test_ch_07b_a_transient_pdf_render_error_stays_retryable`

### CH-13 — P2 — A WhatsApp network reset escapes as an exception

**What happened.** With `ENABLE_WHATSAPP_CLOUD` on, credentials present, and `opt_in=True`, `send_whatsapp_template` calls `requests.post` and does not catch `requests.ConnectionError`. The call raised `ConnectionError: reset`. An HTTP 4xx/5xx from Meta is turned into `mode=failed`. A dropped connection is not.

**Impact.** Invoice share, the customer portal, and the assistant call this function on the request path. A Meta blip becomes a 500 for that action. The invoice is already completed when share is a separate action. The user does not receive the `wa.me` link that the Cloud-off path already returns.

**Fix.** Catch `requests.RequestException` around the Cloud POST and return `mode=failed` (or the `wa.me` link) with the error text in `raw`. Do not POST when `opt_in` is false. That opt-in gate already holds.

**Test.** `tests/test_chaos_resilience.py::test_ch_13_whatsapp_cloud_outage_returns_a_result_instead_of_raising`

### CH-16 — P2 — A crashed Complete bricks the same Idempotency-Key for a day

**What happened.** An in-flight `IdempotencyRecord` for scope `sales_invoice_complete` was aged to 16 minutes, with an empty `resource_id` and a blank `request_hash`. The invoice was still `DRAFT`. `POST /complete/` with the same `Idempotency-Key` returned **409** `idempotency_in_flight`: "A request with this Idempotency-Key is already in progress." `begin_record` refuses to reclaim any money scope, including this one, no matter how old the row is. `prune_idempotency_records_task` deletes in-flight rows only after 24 hours.

**Impact.** A client that retries the same key, which is the correct retry, cannot finish the draft until the next daily prune. Stock was not posted and the number was not taken, so the draft is safe to complete. A different key would start a new claim. The 15-minute `IN_FLIGHT_STALE_SECONDS` window is the bound documented for the slowest protected operation, and money scopes skip it.

**Fix.** After `IN_FLIGHT_STALE_SECONDS`, release a money in-flight row whose `resource_id` is empty so the same key can run Complete. Keep the 409 inside that window so a still-running request is not double-posted. Keep the 24-hour prune as the backstop.

**Test.** `tests/test_chaos_resilience.py::test_ch_16_a_stale_in_flight_complete_key_can_finish_a_still_draft_invoice`

## What held under injection

| Experiment | Result |
| --- | --- |
| CH-01 Cache flush, then the same Complete key | One sale movement. A different body on the same key returned 422 and left `grand_total` unchanged. |
| CH-02 `RuntimeError` inside stock posting | Invoice stayed `DRAFT`, number blank, `stock_balances.on_hand` unchanged, no `SALE` movement. |
| CH-03 Other tenant reads the completed invoice | 404. No stock row on the other company. |
| CH-04 Webhook crash, provider retry, then dead-letter replay | One receipt, link `PAID`. The third delivery did not add a receipt. |
| CH-07 Stale `QUEUED` PDF versus stale `FAILED` | Only the queued invoice was requeued. The owner hook ran once. |
| CH-08 Recurring beat during a soft-closed month | No invoice was created and none was completed. |
| CH-10 Complaints flag turned off mid-flight | `create-credit-note` returned 404 and wrote no note. After approval, two posts created one note. |
| CH-06, CH-09, CH-11, CH-12, CH-14, CH-15 | Already locked by the Phase 0 tests named in the module docstring. They passed there. |
| Offline POS date pin | `flushPosCheckout.test.ts`, 9 passed. A retry keeps the `invoiceDate` from the first attempt. |

## Not run

Two concurrent `SalesService.complete` calls racing the next invoice number. SQLite does not prove that lock. Run `pytest -m postgres` against the concurrency suite before calling the number sequence chaos-proof.
