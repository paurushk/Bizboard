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
          // BB-000737: offline nav must not serve the SPA shell as a fake online app
          // when the network errors — handlerDidError returns offline.html.
          // UXW2-004: keep SPA navigateFallback for deep links; raise timeout so
          // slow networks are not misclassified as offline.
          navigateFallback: '/offline.html',
          navigateFallbackDenylist: [/^\/api\//],
          runtimeCaching: [
            // BB-000738: never NetworkFirst-cache authenticated /api (no status-0 poison).
            {
              urlPattern: ({ request }) => request.mode === 'navigate',
              handler: 'NetworkFirst',
              options: {
                cacheName: 'bizboard-pages',
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
      exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**', '**/e2e-golden/**'],
    },
  };
});
