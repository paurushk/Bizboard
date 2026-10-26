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
 * latency, not real endpoint latency. Since 2026-10-23 setup() uses the session cookies
 * (staging is cookie-only) and aborts the run when sign-in gives no session.
 *
 * D-10/D-11 (2026-10-24): STAFF_EMAILS gives each VU its own login (see k6_mixed.js), and
 * Completes run at a fixed COMPLETES_PER_MIN (default 50) because the server allows 60 per
 * minute per company; faster than that measures 429s, not Complete latency.
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

// Scenarios run one after another so a slow report cannot queue behind list
// or Complete on the default 2 sync workers. K6_ONLY=list|dashboard|reports|all.
// A 30-minute soak belongs in load/k6_mixed.js. Access tokens last 15 minutes
// (JWT_ACCESS_MINUTES); set JWT_ACCESS_MINUTES=60 on staging before a soak.
const ONLY = __ENV.K6_ONLY || "all";
// Under the 60/min per-company Complete limit (D-11).
const COMPLETES_PER_MIN = Number(__ENV.COMPLETES_PER_MIN || "50");
// One login per VU (D-10); setup() signs them in one every LOGIN_GAP_S, under the 10/min login limit.
const STAFF_EMAILS = (__ENV.STAFF_EMAILS || "").split(",").map((s) => s.trim()).filter(Boolean);
const LOGIN_GAP_S = Number(__ENV.LOGIN_GAP_S || "7");

function wants(name) {
  return ONLY === "all" || ONLY === name;
}

const scenarios = {};
if (wants("list")) {
  scenarios.list_complete_list = {
    executor: "constant-vus",
    vus: 10,
    duration: "2m",
    exec: "listInvoices",
    startTime: "0s",
  };
  scenarios.list_complete_complete = {
    executor: "constant-arrival-rate",
    rate: COMPLETES_PER_MIN,
    timeUnit: "1m",
    duration: "2m",
    preAllocatedVUs: 5,
    maxVUs: 10,
    exec: "completeDraft",
    startTime: "10s",
  };
}
if (wants("dashboard")) {
  scenarios.dashboard = {
    executor: "constant-vus",
    vus: 5,
    duration: "1m",
    exec: "dashboard",
    startTime: ONLY === "all" ? "2m30s" : "0s",
  };
}
if (wants("reports")) {
  scenarios.reports = {
    executor: "constant-vus",
    vus: 2,
    duration: "1m",
    exec: "reports",
    startTime: ONLY === "all" ? "4m" : "0s",
  };
}

const thresholds = { http_req_failed: ["rate<0.05"] };
if (wants("list")) {
  thresholds["http_req_duration{name:invoice_list}"] = ["p(95)<2000"];
  thresholds["http_req_duration{name:invoice_complete}"] = ["p(95)<800"];
}
if (wants("dashboard")) {
  thresholds["http_req_duration{name:dashboard}"] = ["p(95)<500"];
}
if (wants("reports")) {
  thresholds["http_req_duration{name:report_sales}"] = ["p(95)<8000"];
  thresholds["http_req_duration{name:report_gstr1}"] = ["p(95)<8000"];
}

export const options = {
  scenarios,
  thresholds,
  setupTimeout: `${Math.ceil(Math.max(1, STAFF_EMAILS.length) * (LOGIN_GAP_S + 2)) + 60}s`,
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

// Staging is cookie-only: login sets the session cookies and returns no access token, so
// send those cookies (plus X-CSRFToken) on every request. A bearer token in the body, where a
// backend still sends one, is used as well. No session = abort the run: a script whose VUs
// silently skip their work reports green thresholds over zero requests (2026-10-23 dry run).
function signIn(email) {
  const login = http.post(
    `${BASE}/api/v1/auth/login/`,
    JSON.stringify({ email, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "login" } },
  );
  const parts = [];
  let csrf = "";
  for (const name in login.cookies) {
    const jar = login.cookies[name];
    if (jar && jar.length) {
      parts.push(`${name}=${jar[0].value}`);
      if (name === "csrftoken") csrf = jar[0].value;
    }
  }
  let access = null;
  try {
    const body = login.json();
    access = (body && body.data && body.data.access) || (body && body.access) || null;
  } catch (e) {
    access = null;
  }
  if (login.status !== 200 || (parts.length === 0 && !access)) {
    throw new Error(`sign-in for ${email} gave no session (HTTP ${login.status}; wrong password, two-step, or throttled)`);
  }
  const headers = { "Content-Type": "application/json" };
  if (parts.length) headers.Cookie = parts.join("; ");
  if (csrf) headers["X-CSRFToken"] = csrf;
  if (access) headers.Authorization = `Bearer ${access}`;
  return headers;
}

export function setup() {
  const emails = STAFF_EMAILS.length ? STAFF_EMAILS : [EMAIL];
  if (!emails[0] || !PASSWORD) throw new Error("EMAIL (or STAFF_EMAILS) and PASSWORD are required.");
  const sessions = [];
  emails.forEach((email, i) => {
    if (i > 0) sleep(LOGIN_GAP_S);
    sessions.push(signIn(email));
  });
  return { sessions };
}

// VU n uses login n, wrapping when there are fewer logins than VUs.
function sessionFor(data) {
  const sessions = (data && data.sessions) || [];
  return sessions.length ? sessions[(__VU - 1) % sessions.length] : null;
}

export function listInvoices(data) {
  const headers = sessionFor(data);
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
  const headers = sessionFor(data);
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

export function dashboard(data) {
  const headers = sessionFor(data);
  if (!headers) {
    sleep(1);
    return;
  }
  const res = http.get(`${BASE}/api/v1/dashboard/`, {
    headers,
    tags: { name: "dashboard" },
  });
  check(res, { "dashboard succeeded (2xx)": (r) => r.status >= 200 && r.status < 300 });
  sleep(0.5);
}

export function reports(data) {
  const headers = sessionFor(data);
  if (!headers) {
    sleep(1);
    return;
  }
  const period = __ENV.K6_PERIOD || "2026-09";
  const sales = http.get(
    `${BASE}/api/v1/reports/sales-register/?date_from=${period}-01&date_to=${period}-28&page=1&page_size=50`,
    { headers, tags: { name: "report_sales" } },
  );
  check(sales, { "sales register succeeded (2xx)": (r) => r.status >= 200 && r.status < 300 });
  const gstr = http.get(`${BASE}/api/v1/reports/gstr1/?period=${period}&format=json`, {
    headers,
    tags: { name: "report_gstr1" },
  });
  check(gstr, { "gstr1 succeeded (2xx)": (r) => r.status >= 200 && r.status < 300 });
  sleep(1);
}
