/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import path from 'node:path';

export default defineConfig(({ command, mode }) => {
  if (command === 'build') {
    delete process.env.VITE_PILOT_ADVANCED;
    delete process.env.VITE_USE_MOCKS;
  }
  if (
    (process.env.NODE_ENV === 'production' || command === 'build') &&
    process.env.VITE_USE_MOCKS === 'true'
  ) {
    throw new Error('VITE_USE_MOCKS must not be enabled for production builds');
  }
  if (
    (process.env.NODE_ENV === 'production' || command === 'build') &&
    process.env.VITE_PILOT_ADVANCED === 'true'
  ) {
    throw new Error('VITE_PILOT_ADVANCED must not be enabled for production builds');
  }

  const lockProdFlags = command === 'build' || mode === 'production';

  return {
    define: {
      // Never honor PILOT_ADVANCED from a parent shell during `vite --mode e2e`.
      'import.meta.env.VITE_PILOT_ADVANCED': JSON.stringify('false'),
      // Production builds must not ship mocks. Dev / e2e read `.env` / `.env.e2e`.
      ...(lockProdFlags
        ? { 'import.meta.env.VITE_USE_MOCKS': JSON.stringify('false') }
        : {}),
    },
    plugins: [
      react(),
      VitePWA({
        // F1-003: 'prompt' so pwa.ts's onNeedRefresh confirm actually fires —
        // 'autoUpdate' made that a dead handler and silently reloaded the tab
        // on every deploy, losing unsaved editor / POS state.
        registerType: 'prompt',
        includeAssets: ['favicon.svg', 'offline.html', 'manifest.webmanifest'],
        manifest: false,
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2,webmanifest}'],
          // Deep links are NetworkFirst against the network (nginx returns index.html).
          // offline.html is only the handlerDidError document when that fetch fails.
          // navigateFallback must stay null. Pointing it at offline.html serves the
          // offline page for every non-precached URL while the network is up.
          // Pointing it at index.html hits the precache and skips this NetworkFirst rule.
          // vite-plugin-pwa's own default is "index.html"; null overrides that.
          // UXW2-004: networkTimeoutSeconds stays 10.
          navigateFallback: null,
          runtimeCaching: [
            // BB-000738: never NetworkFirst-cache authenticated /api (no status-0 poison).
            {
              urlPattern: ({ request }) => request.mode === 'navigate',
              handler: 'NetworkFirst',
              options: {
                cacheName: 'bizboard-pages',
                // Stay at 10s. A longer wait keeps a dead shell on screen; Try again unregisters the worker.
                networkTimeoutSeconds: 10,
                plugins: [
                  {
                    handlerDidError: async () => globalThis.caches.match('/offline.html'),
                  },
                ],
              },
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'mui-vendor': ['@mui/material', '@mui/icons-material'],
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'query-vendor': ['@tanstack/react-query'],
          },
        },
      },
    },
    // Vitest extends Vite config with test options.
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: true,
      // The editor and list-page tests mount whole screens; under a full parallel run 15s was not enough.
      testTimeout: 30_000,
      exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**', '**/e2e-golden/**', '**/e2e-sw/**'],
    },
  };
});
