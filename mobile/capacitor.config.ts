import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'in.bizboard.app',
  appName: 'Bizboard',
  webDir: '../web/dist',
  server: {
    androidScheme: 'https',
    // Do not set server.url to a remote API in the packaged app.
    // Capacitor iOS is not a supported shipping target.
  },
};

export default config;
