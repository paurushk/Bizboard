import type { CapacitorConfig } from '@capacitor/cli';

const serverUrl = (process.env.CAPACITOR_SERVER_URL || process.env.VITE_APP_ORIGIN || '').trim();

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
