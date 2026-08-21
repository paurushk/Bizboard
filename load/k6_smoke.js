/**
 * Wave 16A / Wave 17A — k6 smoke: health + auth + create-draft (MVP load).
 *
 * Usage:
 *   k6 run -e BASE_URL=http://localhost:8000 load/k6_smoke.js
 *   k6 run -e BASE_URL=... -e EMAIL=... -e PASSWORD=... load/k6_smoke.js
 *
 * Not a soak/capacity proof for 10k tenants — document as MVP load harness.
 */
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 5,
  duration: "30s",
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<2000"],
  },
};

const BASE = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.EMAIL || "";
const PASSWORD = __ENV.PASSWORD || "";

export default function () {
  const health = http.get(`${BASE}/api/v1/health/`);
  check(health, {
    "health status is 200": (r) => r.status === 200,
  });

  if (EMAIL && PASSWORD) {
    const login = http.post(
      `${BASE}/api/v1/auth/login/`,
      JSON.stringify({ email: EMAIL, password: PASSWORD }),
      { headers: { "Content-Type": "application/json" } },
    );
    check(login, {
      "login ok": (r) => r.status === 200 || r.status === 201,
    });
    const jar = http.cookieJar();
    const cookies = jar.cookiesForURL(BASE);
    const headers = { "Content-Type": "application/json" };

    const list = http.get(`${BASE}/api/v1/sales/invoices/?page=1`, {
      cookies,
      headers,
    });
    check(list, {
      "invoice list not 5xx": (r) => r.status < 500,
    });

    // Wave 17A: authenticated create-draft scenario (expects customer id env or skips).
    const customerId = __ENV.CUSTOMER_ID || "";
    const productId = __ENV.PRODUCT_ID || "";
    if (customerId && productId) {
      const draft = http.post(
        `${BASE}/api/v1/sales/invoices/`,
        JSON.stringify({
          customer: Number(customerId),
          invoice_type: "NON_GST",
          items: [
            {
              product: Number(productId),
              quantity: "1",
              unit_price: "10",
              gst_rate: "0",
            },
          ],
        }),
        { cookies, headers },
      );
      check(draft, {
        "create-draft not 5xx": (r) => r.status < 500,
        "create-draft accepted": (r) => r.status === 201 || r.status === 200 || r.status === 400,
      });
    }
  }

  sleep(0.5);
}
