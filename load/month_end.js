/**
 * WP-RS1: month-end and GST-deadline load. Around the 10th, 11th and 20th most tenants open their
 * GSTR-1 / GSTR-3B worksheets and download the Excel files and invoice PDFs within a couple of
 * hours, while normal invoicing carries on. This scenario puts that on staging:
 *
 *   - gst:      70% of the tenant accounts given (TENANTS) each open GSTR-1 and GSTR-3B for the
 *               period and download both as xlsx, then the dashboard — their arrivals spread evenly
 *               over DURATION, so the invoice latency below is measured during the whole peak;
 *   - invoices: a steady stream of draft Completes on the large tenant (DRAFT_INVOICE_IDS), as in
 *               k6_mixed.js, so invoicing latency is measured under the GST peak.
 *
 *   k6 run -e BASE_URL=https://staging.example \
 *     -e TENANTS="owner1@t1.test:pass1,owner2@t2.test:pass2,..." \
 *     -e TOTP_SECRETS="owner1@t1.test=JBSWY3DPEHPK3PXP,owner2@t2.test=..."  *     -e PERIOD=2026-09 -e DURATION=2h \
 *     -e EMAIL=... -e PASSWORD=... -e DRAFT_INVOICE_IDS=$(python manage.py seed_draft_pool --count 3000 --company "Load Tenant") \
 *     load/month_end.js
 *
 * Locally (against the large-tenant seed, load/SEED_50K.md) use DURATION=10m and a few tenants.
 * Staging must set JWT_ACCESS_MINUTES >= the run length. Staging is cookie-only (no Bearer token,
 * no access token in the login body), so the script signs each tenant in once in setup() — paced
 * under the 10/min per-address login limit — and sends the session cookies (plus X-CSRFToken on
 * the Completes). Before the run: every tenant account has ENABLE_GSTR granted and has finished
 * two-step enrolment. Owners and accountants must use two-step, so give each one's authenticator
 * secret (the base32 key shown at enrolment) in TOTP_SECRETS="owner1@t1.test=BASE32,..."; setup()
 * answers the two-step challenge with the current code. An account still asked to enrol gets no
 * session, and setup() stops the run if any sign-in gets no session. Record the run in
 * docs/ops/LOAD_RESULTS_TEMPLATE.md ("Month-end GST peak"); pre-scale workers as in
 * docs/ops/WORKER_SCALE.md#month-end-and-gst-deadlines.
 *
 * Gate: worksheet p95 < 8s, xlsx p95 < 15s, invoice Complete p95 < 2s during the peak, errors < 1%.
 */
import http from "k6/http";
import { check, sleep } from "k6";
import crypto from "k6/crypto";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const PERIOD = __ENV.PERIOD || "";
const DURATION = __ENV.DURATION || "2h";
const SHARE = Number(__ENV.SHARE || "0.7");
// The login throttle is 10/min per address; one sign-in every 7 s stays under it.
const LOGIN_GAP_S = Number(__ENV.LOGIN_GAP_S || "7");

function seconds(text) {
  const m = /^(\d+(?:\.\d+)?)\s*(h|m|s)?$/.exec(String(text).trim());
  if (!m) return 7200;
  const n = Number(m[1]);
  return m[2] === "h" ? n * 3600 : m[2] === "m" ? n * 60 : n;
}

// Authenticator secrets by email, for accounts that must pass two-step (owners, accountants).
const totpSecrets = {};
for (const pair of (__ENV.TOTP_SECRETS || "").split(",").map((s) => s.trim()).filter(Boolean)) {
  const i = pair.indexOf("=");
  if (i > 0) totpSecrets[pair.slice(0, i).trim().toLowerCase()] = pair.slice(i + 1).trim();
}

function base32Bytes(secret) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/[\s=]/g, "").toUpperCase()) {
    const v = alphabet.indexOf(ch);
    if (v < 0) throw new Error("TOTP secret is not base32");
    bits += v.toString(2).padStart(5, "0");
  }
  const out = new Uint8Array(Math.floor(bits.length / 8));
  for (let i = 0; i < out.length; i++) out[i] = parseInt(bits.slice(i * 8, i * 8 + 8), 2);
  return out.buffer;
}

// RFC 6238 code (SHA-1, 30 s, 6 digits), the same as the authenticator app shows.
export function totp(secret, nowMs = Date.now()) {
  const counter = new Uint8Array(8);
  let step = Math.floor(nowMs / 30000);
  for (let i = 7; i >= 0; i--) {
    counter[i] = step & 0xff;
    step = Math.floor(step / 256);
  }
  const mac = new Uint8Array(crypto.hmac("sha1", base32Bytes(secret), counter.buffer, "binary"));
  const o = mac[mac.length - 1] & 0x0f;
  const n = ((mac[o] & 0x7f) << 24) | (mac[o + 1] << 16) | (mac[o + 2] << 8) | mac[o + 3];
  return String(n % 1000000).padStart(6, "0");
}

const tenants = new SharedArray("tenants", function () {
  const all = (__ENV.TENANTS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((pair) => {
      // An email never contains ":", a password may: split on the first one.
      const i = pair.indexOf(":");
      return { email: pair.slice(0, i), password: pair.slice(i + 1) };
    });
  return all.slice(0, Math.max(1, Math.round(all.length * SHARE)));
});

const draftPool = new SharedArray("draftInvoiceIds", function () {
  const raw = __ENV.DRAFT_INVOICE_IDS || "";
  return raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : [];
});

export const options = {
  // setup() signs every tenant in, one every LOGIN_GAP_S seconds.
  setupTimeout: `${Math.ceil((tenants.length + 1) * (LOGIN_GAP_S + 2)) + 60}s`,
  scenarios: {
    gst: {
      // One VU per tenant, each starting at its own point in the window (see gst()).
      executor: "per-vu-iterations",
      vus: Math.max(1, tenants.length),
      iterations: 1,
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

function session(email, password) {
  let res = http.post(
    `${BASE}/api/v1/auth/login/`,
    JSON.stringify({ email, password }),
    { headers: { "Content-Type": "application/json" }, tags: { name: "login" } },
  );
  // Two-step: the login answers with a challenge token and sets no cookies.
  let body = {};
  try {
    body = res.json() || {};
  } catch (e) {
    body = {};
  }
  const data = body.data || body;
  const mfaToken = data.mfaToken || data.mfa_token;
  if (res.status === 200 && (data.mfaRequired || data.mfa_required) && mfaToken) {
    const secret = totpSecrets[email.toLowerCase()];
    if (!secret) return null;
    res = http.post(
      `${BASE}/api/v1/auth/mfa/verify/`,
      JSON.stringify({ mfaToken, code: totp(secret) }),
      { headers: { "Content-Type": "application/json" }, tags: { name: "login_mfa" } },
    );
  }
  const parts = [];
  let csrf = "";
  for (const name in res.cookies) {
    const jar = res.cookies[name];
    if (jar && jar.length) {
      parts.push(`${name}=${jar[0].value}`);
      if (name === "csrftoken") csrf = jar[0].value;
    }
  }
  // A 200 without cookies is a two-step challenge or enrolment: no session.
  if (res.status !== 200 || parts.length === 0) return null;
  const headers = { "Content-Type": "application/json", Cookie: parts.join("; ") };
  if (csrf) headers["X-CSRFToken"] = csrf;
  return headers;
}

export function setup() {
  const sessions = [];
  for (const t of tenants) {
    const headers = session(t.email, t.password);
    if (!headers) {
      throw new Error(
        `sign-in for ${t.email} gave no session (wrong password, two-step without a TOTP_SECRETS entry, not enrolled, or throttled)`,
      );
    }
    sessions.push(headers);
    sleep(LOGIN_GAP_S);
  }
  const email = __ENV.EMAIL || "";
  const password = __ENV.PASSWORD || "";
  let invoiceHeaders = null;
  if (email && password) {
    invoiceHeaders = session(email, password);
    if (!invoiceHeaders) throw new Error(`sign-in for ${email} gave no session`);
  }
  return { sessions, invoiceHeaders };
}

function period() {
  if (PERIOD) return PERIOD;
  // The previous month, from the 1st (setMonth on the 29th-31st would roll into this month).
  const now = new Date();
  const d = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function gst(data) {
  const index = (__VU - 1) % Math.max(1, tenants.length);
  const headers = data && data.sessions && data.sessions[index];
  if (!headers) return;
  // Arrivals spread evenly across the window like real owners, not all in the first minutes.
  sleep((index / Math.max(1, tenants.length)) * seconds(DURATION) * 0.9);
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
  const index = exec.scenario.iterationInTest;  // unique across the scenario: each draft once
  if (index >= draftPool.length) return;
  const res = http.post(`${BASE}/api/v1/sales/invoices/${draftPool[index]}/complete/`, "{}", {
    headers,
    tags: { name: "invoice_complete" },
  });
  check(res, { "complete 2xx": (r) => r.status >= 200 && r.status < 300 });
}
