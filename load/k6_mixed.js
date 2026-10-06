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
 * Gate (ISO score 3): no tagged request p95 > 8s, error rate < 0.5%.
 * Target SLOs are recorded by k6_slo.js, not enforced here.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

export const options = {
  scenarios: {
    reads: {
      executor: "ramping-vus",
      startVUs: 4,
      stages: [
        { duration: "2m", target: 18 },
        { duration: "26m", target: 18 },
        { duration: "2m", target: 0 },
      ],
      exec: "read",
    },
    writes: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "2m", target: 7 },
        { duration: "26m", target: 7 },
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
const DRAFT_IDS_RAW = __ENV.DRAFT_INVOICE_IDS || "";

const draftPool = new SharedArray("draftInvoiceIds", function () {
  return DRAFT_IDS_RAW
    ? DRAFT_IDS_RAW.split(",").map((s) => s.trim()).filter(Boolean)
    : [];
});

export function setup() {
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

export function read(data) {
  const headers = data && data.headers;
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
  const headers = data && data.headers;
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
  sleep(2);
}
