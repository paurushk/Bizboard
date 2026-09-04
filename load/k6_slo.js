/**
 * X-01 — list + Complete against adopted SLOs.
 *
 * Staging, 50k-invoice tenant, ex-PDF / ex-GSP. Local runs are allowed to miss
 * thresholds; attach numbers to docs/roadmap/ticket-logs/X-01.md, do not invent them.
 *
 *   k6 run -e BASE_URL=... -e EMAIL=... -e PASSWORD=... -e DRAFT_INVOICE_ID=... load/k6_slo.js
 */
import http from "k6/http";
import { check, sleep } from "k6";

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

function authHeaders() {
  // M1-026: capture the bearer token from the login body and send it on every
  // subsequent request. Without this, k6's implicit cookie jar was the only
  // thing carrying "auth" — if the backend issues a bearer token in the body
  // (it does: {success, data: {access, ...}}) rather than a cookie, every
  // later call ran unauthenticated and the p95 thresholds below measured
  // 401/403 rejection latency, not real endpoint latency.
  if (!EMAIL || !PASSWORD) return null;
  const login = http.post(
    `${BASE}/api/v1/auth/login/`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "login" } },
  );
  if (login.status !== 200 && login.status !== 201) return null;
  let access = null;
  try {
    const body = login.json();
    access = (body && body.data && body.data.access) || (body && body.access) || null;
  } catch (e) {
    access = null;
  }
  if (!access) return null;
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${access}`,
  };
}

export function listInvoices() {
  const headers = authHeaders();
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

export function completeDraft() {
  const headers = authHeaders();
  if (!headers || !DRAFT_ID) {
    sleep(1);
    return;
  }
  const res = http.post(`${BASE}/api/v1/sales/invoices/${DRAFT_ID}/complete/`, "{}", {
    headers,
    tags: { name: "invoice_complete" },
  });
  check(res, {
    "complete succeeded (2xx)": (r) => r.status >= 200 && r.status < 300,
  });
  sleep(1);
}
