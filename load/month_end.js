/**
 * WP-RS1: month-end and GST-deadline load. Around the 10th, 11th and 20th most tenants open their
 * GSTR-1 / GSTR-3B worksheets and download the Excel files and invoice PDFs within a couple of
 * hours, while normal invoicing carries on. This scenario puts that on staging:
 *
 *   - gst:      70% of the tenant accounts given (TENANTS) each open GSTR-1 and GSTR-3B for the
 *               period and download both as xlsx, then the dashboard — spread over DURATION;
 *   - invoices: a steady stream of draft Completes on the large tenant (DRAFT_INVOICE_IDS), as in
 *               k6_mixed.js, so invoicing latency is measured under the GST peak.
 *
 *   k6 run -e BASE_URL=https://staging.example \
 *     -e TENANTS="owner1@t1.test:pass1,owner2@t2.test:pass2,..." \
 *     -e PERIOD=2026-09 -e DURATION=2h \
 *     -e EMAIL=... -e PASSWORD=... -e DRAFT_INVOICE_IDS=$(python manage.py seed_draft_pool --count 3000 --company "Load Tenant") \
 *     load/month_end.js
 *
 * Locally (against the large-tenant seed, load/SEED_50K.md) use DURATION=10m and a few tenants.
 * Staging must set JWT_ACCESS_MINUTES >= the run length. Record the run in
 * docs/ops/LOAD_RESULTS_TEMPLATE.md ("Month-end GST peak"); pre-scale workers as in
 * docs/ops/WORKER_SCALE.md#month-end-and-gst-deadlines.
 *
 * Gate: worksheet p95 < 8s, xlsx p95 < 15s, invoice Complete p95 < 2s during the peak, errors < 1%.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const PERIOD = __ENV.PERIOD || "";
const DURATION = __ENV.DURATION || "2h";
const SHARE = Number(__ENV.SHARE || "0.7");

const tenants = new SharedArray("tenants", function () {
  const all = (__ENV.TENANTS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((pair) => {
      const i = pair.lastIndexOf(":");
      return { email: pair.slice(0, i), password: pair.slice(i + 1) };
    });
  return all.slice(0, Math.max(1, Math.round(all.length * SHARE)));
});

const draftPool = new SharedArray("draftInvoiceIds", function () {
  const raw = __ENV.DRAFT_INVOICE_IDS || "";
  return raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : [];
});

export const options = {
  scenarios: {
    gst: {
      executor: "shared-iterations",
      vus: Math.max(1, Math.min(50, tenants.length)),
      iterations: Math.max(1, tenants.length),
      maxDuration: DURATION,
      exec: "gst",
    },
    invoices: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.COMPLETES_PER_MIN || "20"),
      timeUnit: "1m",
      duration: DURATION,
      preAllocatedVUs: 5,
      exec: "invoice",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{name:gstr1}": ["p(95)<8000"],
    "http_req_duration{name:gstr3b}": ["p(95)<8000"],
    "http_req_duration{name:gstr1_xlsx}": ["p(95)<15000"],
    "http_req_duration{name:gstr3b_xlsx}": ["p(95)<15000"],
    "http_req_duration{name:invoice_complete}": ["p(95)<2000"],
  },
};

function login(email, password) {
  const res = http.post(
    `${BASE}/api/v1/auth/login/`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "login" } },
  );
  if (res.status !== 200) return null;
  let access = null;
  try {
    const body = res.json();
    access = (body && body.data && body.data.access) || (body && body.access) || null;
  } catch (e) {
    access = null;
  }
  return access ? { "Content-Type": "application/json", Authorization: `Bearer ${access}` } : null;
}

export function setup() {
  const email = __ENV.EMAIL || "";
  const password = __ENV.PASSWORD || "";
  return { invoiceHeaders: email && password ? login(email, password) : null };
}

function period() {
  if (PERIOD) return PERIOD;
  const d = new Date();
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function gst() {
  const tenant = tenants[exec.scenario.iterationInTest % tenants.length];
  const headers = tenant && login(tenant.email, tenant.password);
  if (!headers) {
    sleep(1);
    return;
  }
  // Spread arrivals across the window like real owners, not all in the first second.
  sleep(Math.random() * 30);
  const p = period();
  for (const [name, path] of [["gstr1", "gstr1"], ["gstr3b", "gstr3b"]]) {
    const view = http.get(`${BASE}/api/v1/reports/${path}/?period=${p}`, { headers, tags: { name } });
    check(view, { [`${name} 2xx`]: (r) => r.status >= 200 && r.status < 300 });
    sleep(2 + Math.random() * 5);
    const xlsx = http.get(`${BASE}/api/v1/reports/${path}/?period=${p}&format=xlsx`, {
      headers,
      tags: { name: `${name}_xlsx` },
      responseType: "none",
    });
    check(xlsx, { [`${name} xlsx 2xx`]: (r) => r.status >= 200 && r.status < 300 });
    sleep(1 + Math.random() * 3);
  }
  const dash = http.get(`${BASE}/api/v1/dashboard/`, { headers, tags: { name: "dashboard" } });
  check(dash, { "dashboard 2xx": (r) => r.status >= 200 && r.status < 300 });
}

export function invoice(data) {
  const headers = data && data.invoiceHeaders;
  if (!headers || draftPool.length === 0) {
    sleep(1);
    return;
  }
  const index = exec.scenario.iterationInTest;
  if (index >= draftPool.length) return;
  const res = http.post(`${BASE}/api/v1/sales/invoices/${draftPool[index]}/complete/`, "{}", {
    headers,
    tags: { name: "invoice_complete" },
  });
  check(res, { "complete 2xx": (r) => r.status >= 200 && r.status < 300 });
}
