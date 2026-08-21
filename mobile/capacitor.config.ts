import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'in.bizboard.app',
  appName: 'Bizboard',
  webDir: '../web/dist',
  server: {
    androidScheme: 'https',
  },
};

export default config;
