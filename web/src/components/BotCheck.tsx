import { useEffect, useRef } from 'react';
import Box from '@mui/material/Box';
import { onBotTokenConsumed, setBotToken, turnstileSiteKey } from '@/auth/botCheck';
import { t } from '@/i18n';

type Turnstile = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile?: Turnstile;
  }
}

const SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
let scriptPromise: Promise<Turnstile> | null = null;

function loadTurnstile(): Promise<Turnstile> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = SCRIPT_SRC;
      el.async = true;
      el.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error('turnstile')));
      el.onerror = () => {
        scriptPromise = null;
        reject(new Error('turnstile'));
      };
      document.head.appendChild(el);
    });
  }
  return scriptPromise;
}

/**
 * WP-AB2: Cloudflare Turnstile on sign-up, OTP and reset. Loads only on those screens and only
 * when VITE_TURNSTILE_SITE_KEY is set; renders nothing otherwise. The token goes to
 * `@/auth/botCheck`, which apiClient attaches to the next pre-login request.
 */
export function BotCheck() {
  const siteKey = turnstileSiteKey();
  const host = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!siteKey || !host.current) return undefined;
    let widgetId: string | null = null;
    let cancelled = false;
    const el = host.current;
    loadTurnstile()
      .then((ts) => {
        if (cancelled) return;
        widgetId = ts.render(el, {
          sitekey: siteKey,
          callback: (value: string) => setBotToken(value),
          'expired-callback': () => setBotToken(null),
          'error-callback': () => setBotToken(null),
        });
      })
      .catch(() => {
        /* The server refuses without a token and says why; nothing more to do here. */
      });
    // A token is single-use: once a request took it, get a fresh one.
    const off = onBotTokenConsumed(() => {
      if (widgetId && window.turnstile) window.turnstile.reset(widgetId);
    });
    return () => {
      cancelled = true;
      off();
      if (widgetId && window.turnstile) window.turnstile.remove(widgetId);
      setBotToken(null);
    };
  }, [siteKey]);

  if (!siteKey) return null;
  return <Box ref={host} aria-label={t('auth.botCheckLabel')} sx={{ minHeight: 65, my: 1 }} />;
}
