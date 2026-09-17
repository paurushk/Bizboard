/**
 * X-01 — list + Complete against adopted SLOs.
 *
 * Staging, 50k-invoice tenant, ex-PDF / ex-GSP. Local runs are allowed to miss
 * thresholds; attach numbers to docs/roadmap/ticket-logs/X-01.md, do not invent them.
 *
 *   export DRAFT_INVOICE_IDS=$(python manage.py seed_draft_pool --count 700)
 *   k6 run -e BASE_URL=... -e EMAIL=... -e PASSWORD=... \
 *       -e DRAFT_INVOICE_IDS=$DRAFT_INVOICE_IDS load/k6_slo.js
 *
 * QOS-0003 (2026-09-12): same fix as k6_smoke.js — authenticate once in
 * setup() instead of once per iteration. With 10+5 VUs re-logging in every
 * ~0.5-1s, the script tripped Bizboard's own 10/min login throttle within
 * seconds, so every measurement after that point was throttle-rejection
 * latency, not real endpoint latency. M1-026's bearer-token capture is kept,
 * just moved to run once.
 *
 * QOS-0003 follow-up: completeDraft() used to hit one hardcoded DRAFT_ID for
 * the whole 2m run — only the first call actually completed it, the other
 * ~314/315 samples were "400 already completed" rejection latency (70-200ms),
 * not real Complete work. It now draws a fresh, not-yet-completed invoice
 * from DRAFT_INVOICE_IDS (seeded via `manage.py seed_draft_pool`) on every
 * iteration. DRAFT_INVOICE_ID (singular) still works as a same-single-draft
 * fallback, with the same caveat as before — size the pool via
 * DRAFT_INVOICE_IDS to get a real signal.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

export const options = {
  scenarios: {
    list: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
      exec: "listInvoices",
    },
    complete: {
      executor: "constant-vus",
      vus: 5,
      duration: "2m",
      exec: "completeDraft",
      startTime: "10s",
    },
  },
  thresholds: {
    "http_req_duration{name:invoice_list}": ["p(95)<2000"],
    "http_req_duration{name:invoice_complete}": ["p(95)<800"],
    http_req_failed: ["rate<0.05"],
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.EMAIL || "";
const PASSWORD = __ENV.PASSWORD || "";
const DRAFT_ID = __ENV.DRAFT_INVOICE_ID || "";
const DRAFT_IDS_RAW = __ENV.DRAFT_INVOICE_IDS || "";

// SharedArray loads/parses the pool once and shares it read-only across VUs.
const draftPool = new SharedArray("draftInvoiceIds", function () {
  return DRAFT_IDS_RAW
    ? DRAFT_IDS_RAW.split(",").map((s) => s.trim()).filter(Boolean)
    : [];
});

export function setup() {
  // M1-026: capture the bearer token from the login body and send it on every
  // subsequent request. Without this, k6's implicit cookie jar was the only
  // thing carrying "auth" — if the backend issues a bearer token in the body
  // (it does: {success, data: {access, ...}}) rather than a cookie, every
  // later call ran unauthenticated and the p95 thresholds below measured
  // 401/403 rejection latency, not real endpoint latency.
  if (!EMAIL || !PASSWORD) return { headers: null };
  const login = http.post(
    `${BASE}/api/v1/auth/login/`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "login" } },
  );
  if (login.status !== 200 && login.status !== 201) return { headers: null };
  let access = null;
  try {
    const body = login.json();
    access = (body && body.data && body.data.access) || (body && body.access) || null;
  } catch (e) {
    access = null;
  }
  if (!access) return { headers: null };
  return {
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access}`,
    },
  };
}

export function listInvoices(data) {
  const headers = data && data.headers;
  if (!headers) {
    sleep(1);
    return;
  }
  const res = http.get(`${BASE}/api/v1/sales/invoices/?page=1&page_size=50`, {
    headers,
    tags: { name: "invoice_list" },
  });
  // M1-026: fail loudly on an auth rejection instead of letting 401/403
  // silently "pass" a <500 check — a green run must mean the endpoint was
  // actually exercised, not that it rejected every request quickly.
  check(res, { "list succeeded (2xx)": (r) => r.status >= 200 && r.status < 300 });
  sleep(0.5);
}

export function completeDraft(data) {
  const headers = data && data.headers;
  if (!headers) {
    sleep(1);
    return;
  }

  let draftId;
  if (draftPool.length > 0) {
    // scenario.iterationInTest is a counter unique across all VUs *in this
    // scenario* (unlike __VU, which is a global VU id with no guaranteed
    // per-scenario range) — exactly one draft per call, no collisions.
    const index = exec.scenario.iterationInTest;
    if (index >= draftPool.length) {
      // Pool exhausted for this run — stop calling the endpoint rather than
      // silently falling back to a re-completion (which would go back to
      // measuring 400-rejection latency, the exact bug this pool fixes).
      sleep(1);
      return;
    }
    draftId = draftPool[index];
  } else if (DRAFT_ID) {
    // Fallback: same single-draft mode as before. Only the first call across
    // the whole run measures a real Complete — use DRAFT_INVOICE_IDS instead.
    draftId = DRAFT_ID;
  } else {
    sleep(1);
    return;
  }

  const res = http.post(`${BASE}/api/v1/sales/invoices/${draftId}/complete/`, "{}", {
    headers,
    tags: { name: "invoice_complete" },
  });
  check(res, {
    "complete succeeded (2xx)": (r) => r.status >= 200 && r.status < 300,
  });
  sleep(1);
}
