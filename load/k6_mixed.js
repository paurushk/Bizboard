/**
 * 30-minute mixed soak. Separate from k6_slo.js so list/Complete numbers
 * are not queued behind a report.
 *
 * Staging must set JWT_ACCESS_MINUTES=60. The access token otherwise expires
 * at 15 minutes and the second half of the run measures 401s.
 *
 *   export DRAFT_INVOICE_IDS=$(python manage.py seed_draft_pool --count 6500 --company "Load Tenant")
 *   k6 run -e BASE_URL=... -e EMAIL=... -e PASSWORD=... \
 *       -e DRAFT_INVOICE_IDS=$DRAFT_INVOICE_IDS load/k6_mixed.js
 *
 * One login cannot stand in for 25 users: the per-user API limit (100 requests / 10 s) is hit by
 * design. Give every virtual user its own login with STAFF_EMAILS (the comma list that
 * `seed_load_tenant --staff 25` prints as staff_emails=..., all sharing PASSWORD). setup() signs
 * them in one every LOGIN_GAP_S seconds, under the 10/min login limit, and VU n uses login n.
 *
 * Gate (ISO score 3): no tagged request p95 > 8s, error rate < 0.5%.
 * Target SLOs are recorded by k6_slo.js, not enforced here.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

// Steady-state minutes between the 2-minute ramps (default 26 = the 30-minute soak).
// SOAK_MINUTES=1 is a quick dry run that the script and login work, not a result.
const SOAK_MINUTES = Number(__ENV.SOAK_MINUTES || "26");
// Writers together stay under the 60/min per-company Complete limit (D-11).
const WRITE_VUS = 7;
const COMPLETES_PER_MIN = Number(__ENV.COMPLETES_PER_MIN || "50");

export const options = {
  // setup() signs every STAFF_EMAILS login in, one every LOGIN_GAP_S seconds.
  setupTimeout: `${Math.ceil(Math.max(1, (__ENV.STAFF_EMAILS || "").split(",").filter((s) => s.trim()).length) * (Number(__ENV.LOGIN_GAP_S || "7") + 2)) + 60}s`,
  scenarios: {
    reads: {
      executor: "ramping-vus",
      startVUs: 4,
      stages: [
        { duration: "2m", target: 18 },
        { duration: `${SOAK_MINUTES}m`, target: 18 },
        { duration: "2m", target: 0 },
      ],
      exec: "read",
    },
    writes: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "2m", target: WRITE_VUS },
        { duration: `${SOAK_MINUTES}m`, target: WRITE_VUS },
        { duration: "2m", target: 0 },
      ],
      exec: "write",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.005"],
    "http_req_duration{name:invoice_list}": ["p(95)<8000"],
    "http_req_duration{name:invoice_detail}": ["p(95)<8000"],
    "http_req_duration{name:dashboard}": ["p(95)<8000"],
    "http_req_duration{name:invoice_complete}": ["p(95)<8000"],
    "http_req_duration{name:search}": ["p(95)<8000"],
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.EMAIL || "";
const PASSWORD = __ENV.PASSWORD || "";
// One login per virtual user (D-10, 2026-10-24); falls back to EMAIL alone.
const STAFF_EMAILS = (__ENV.STAFF_EMAILS || "").split(",").map((s) => s.trim()).filter(Boolean);
const LOGIN_EMAILS = STAFF_EMAILS.length ? STAFF_EMAILS : [EMAIL];
// The login throttle is 10/min per address; one sign-in every 7 s stays under it.
const LOGIN_GAP_S = Number(__ENV.LOGIN_GAP_S || "7");
const DRAFT_IDS_RAW = __ENV.DRAFT_INVOICE_IDS || "";

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
  if (!LOGIN_EMAILS[0] || !PASSWORD) throw new Error("EMAIL (or STAFF_EMAILS) and PASSWORD are required.");
  const sessions = [];
  LOGIN_EMAILS.forEach((email, i) => {
    if (i > 0) sleep(LOGIN_GAP_S);
    sessions.push(signIn(email));
  });
  return { sessions };
}

// VU n (1-based, unique across both scenarios) uses login n, wrapping when there are fewer logins.
function sessionFor(data) {
  const sessions = (data && data.sessions) || [];
  return sessions.length ? sessions[(__VU - 1) % sessions.length] : null;
}

export function read(data) {
  const headers = sessionFor(data);
  if (!headers) {
    sleep(1);
    return;
  }
  const roll = exec.vu.iterationInInstance % 10;
  let res;
  if (roll < 5) {
    res = http.get(`${BASE}/api/v1/sales/invoices/?page=1&page_size=50`, {
      headers,
      tags: { name: "invoice_list" },
    });
    check(res, { "list 2xx": (r) => r.status >= 200 && r.status < 300 });
  } else if (roll < 8) {
    res = http.get(`${BASE}/api/v1/dashboard/`, { headers, tags: { name: "dashboard" } });
    check(res, { "dashboard 2xx": (r) => r.status >= 200 && r.status < 300 });
  } else if (roll < 9) {
    res = http.get(`${BASE}/api/v1/search/?q=load`, { headers, tags: { name: "search" } });
    check(res, { "search 2xx": (r) => r.status >= 200 && r.status < 300 });
  } else {
    res = http.get(`${BASE}/api/v1/sales/invoices/?page=1&page_size=1`, {
      headers,
      tags: { name: "invoice_detail" },
    });
    check(res, { "detail 2xx": (r) => r.status >= 200 && r.status < 300 });
  }
  sleep(0.4);
}

export function write(data) {
  const headers = sessionFor(data);
  if (!headers || draftPool.length === 0) {
    sleep(1);
    return;
  }
  // iterationInTest is unique inside this scenario, so each draft is completed once.
  const index = exec.scenario.iterationInTest;
  if (index >= draftPool.length) {
    sleep(1);
    return;
  }
  const res = http.post(
    `${BASE}/api/v1/sales/invoices/${draftPool[index]}/complete/`,
    "{}",
    { headers, tags: { name: "invoice_complete" } },
  );
  check(res, { "complete 2xx": (r) => r.status >= 200 && r.status < 300 });
  // Each writer waits long enough that all of them together complete COMPLETES_PER_MIN.
  sleep(Math.max(2, (WRITE_VUS * 60) / COMPLETES_PER_MIN));
}
