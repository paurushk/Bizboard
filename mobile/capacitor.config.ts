import type { CapacitorConfig } from '@capacitor/cli';

// M1-010: only an explicit CAPACITOR_SERVER_URL may point the WebView at a
// remote origin — no falling back to the generic VITE_APP_ORIGIN, which any
// web build sets and which could silently ship a device build that loads the
// SPA from an unintended host. It must be https and not localhost.
const rawServerUrl = (process.env.CAPACITOR_SERVER_URL || '').trim();
let serverUrl = '';
if (rawServerUrl) {
  let ok = false;
  try {
    const u = new URL(rawServerUrl);
    ok =
      u.protocol === 'https:' &&
      u.hostname !== 'localhost' &&
      !u.hostname.endsWith('.local');
  } catch {
    ok = false;
  }
  if (!ok) {
    throw new Error(
      `CAPACITOR_SERVER_URL must be an https:// origin (not localhost): got ${rawServerUrl}`,
    );
  }
  serverUrl = rawServerUrl;
}

const config: CapacitorConfig = {
  appId: 'in.bizboard.app',
  appName: 'Bizboard',
  webDir: '../web/dist',
  server: {
    androidScheme: 'https',
    // Load the SPA from the same origin as the API so JWT cookies (SameSite=Lax)
    // stay first-party. Cross-origin WebView + relative /api/v1 will not auth.
    ...(serverUrl ? { url: serverUrl } : {}),
  },
};

export default config;
