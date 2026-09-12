import { expect, test } from '@playwright/test';

/**
 * Golden persona / tenant-isolation run against the LIVE backend (no mocks):
 * two freshly-registered OWNER tenants, and the real DRF `CompanyScopedViewSet`
 * refuses cross-tenant reads / IDOR — proving the isolation the mock suite can
 * only assume.
 *
 * Requires: backend migrated. Run with: npm run test:e2e:golden
 */

function unique() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

const PASSWORD = 'GoldenPersona123!';

async function registerAndLogin(request: import('@playwright/test').APIRequestContext, apiRoot: string) {
  const id = unique();
  const email = `golden-persona-${id}@example.test`;
  const reg = await request.post(`${apiRoot}/auth/register/`, {
    data: {
      companyName: `Golden Persona ${id}`,
      company_name: `Golden Persona ${id}`,
      fullName: 'Persona Owner',
      full_name: 'Persona Owner',
      email,
      password: PASSWORD,
      state: 'Karnataka',
      registrationType: 'UNREGISTERED',
      registration_type: 'UNREGISTERED',
    },
  });
  expect(reg.ok(), `register failed: ${reg.status()} ${await reg.text()}`).toBeTruthy();

  const login = await request.post(`${apiRoot}/auth/login/`, { data: { email, password: PASSWORD } });
  expect(login.ok(), `login failed: ${login.status()} ${await login.text()}`).toBeTruthy();

  // session cookie auth also enforces CSRF on writes — mirror the SPA: fetch the
  // token and send it as X-CSRFToken.
  const csrfRes = await request.get(`${apiRoot}/auth/csrf/`);
  let csrf = '';
  try {
    csrf = String((await csrfRes.json())?.csrfToken ?? (await csrfRes.json())?.token ?? '');
  } catch {
    /* token may only be in the cookie */
  }
  if (!csrf) {
    const cookies = (await request.storageState()).cookies;
    csrf = cookies.find((c) => c.name === 'csrftoken')?.value ?? '';
  }
  return { email, csrf };
}

test('live backend enforces tenant isolation across two OWNER tenants', async ({ playwright, baseURL }) => {
  const apiRoot = (baseURL ?? 'http://127.0.0.1:5173').replace(/\/$/, '') + '/api/v1';

  // --- tenant A: register, log in, create a customer ---
  const ctxA = await playwright.request.newContext();
  const a = await registerAndLogin(ctxA, apiRoot);
  const madeCustomer = await ctxA.post(`${apiRoot}/customers/`, {
    headers: { 'X-CSRFToken': a.csrf },
    data: { name: `A-Only Customer ${unique()}`, state: 'Karnataka' },
  });
  expect(madeCustomer.status(), await madeCustomer.text()).toBe(201);
  const madeBody = await madeCustomer.json();
  const aCustomerId = madeBody.id ?? madeBody.data?.id ?? madeBody.result?.id;
  expect(aCustomerId, JSON.stringify(madeBody)).toBeTruthy();

  // --- tenant B: separate registration + session ---
  const ctxB = await playwright.request.newContext();
  const b = await registerAndLogin(ctxB, apiRoot);

  // B cannot read A's customer by id (IDOR) -> 404, never 200
  const idor = await ctxB.get(`${apiRoot}/customers/${aCustomerId}/`);
  expect(idor.status(), await idor.text()).toBe(404);

  // B cannot mutate A's customer
  const idorPatch = await ctxB.patch(`${apiRoot}/customers/${aCustomerId}/`, {
    headers: { 'X-CSRFToken': b.csrf },
    data: { name: 'hijacked' },
  });
  expect([403, 404]).toContain(idorPatch.status());

  // B's own customer list does not contain A's row
  const bList = await ctxB.get(`${apiRoot}/customers/`);
  expect(bList.ok()).toBeTruthy();
  const bBody = await bList.json();
  const bRows = bBody.results ?? bBody.data?.results ?? bBody.data ?? bBody;
  const bIds = (Array.isArray(bRows) ? bRows : []).map((r: { id?: number }) => r.id);
  expect(bIds).not.toContain(aCustomerId);

  // --- no session at all -> 401 ---
  const anon = await playwright.request.newContext();
  const anonList = await anon.get(`${apiRoot}/customers/`);
  expect(anonList.status()).toBe(401);

  await ctxA.dispose();
  await ctxB.dispose();
  await anon.dispose();
});

test('live backend: an unauthenticated write is rejected before it touches data', async ({
  playwright,
  baseURL,
}) => {
  const apiRoot = (baseURL ?? 'http://127.0.0.1:5173').replace(/\/$/, '') + '/api/v1';
  const anon = await playwright.request.newContext();
  const res = await anon.post(`${apiRoot}/customers/`, { data: { name: 'ghost', state: 'Karnataka' } });
  expect([401, 403]).toContain(res.status());
  await anon.dispose();
});
