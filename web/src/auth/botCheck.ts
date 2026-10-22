/**
 * WP-AB2: the bot-check token for sign-up, OTP and password reset.
 *
 * The <BotCheck /> widget stores the Cloudflare Turnstile token here; apiClient sends it as
 * X-Bot-Token on the pre-login calls that create accounts or send messages, then clears it
 * (a Turnstile token is single-use) so the widget resets for the next try. With no
 * VITE_TURNSTILE_SITE_KEY the widget renders nothing and no header is sent (the backend's
 * BOT_CHECK_PROVIDER=none passes).
 */

export const BOT_CHECK_PATHS = [
  '/auth/register/',
  '/auth/register/otp/request/',
  '/auth/otp/request/',
  '/auth/password/reset/',
  // WP-ID5: a Google sign-up creates an account (the server checks the token only then).
  '/auth/google/',
] as const;

let token: string | null = null;
const listeners = new Set<(value: string | null) => void>();

export function turnstileSiteKey(): string {
  return String(import.meta.env.VITE_TURNSTILE_SITE_KEY ?? '').trim();
}

export function setBotToken(value: string | null): void {
  token = value;
  listeners.forEach((fn) => fn(token));
}

/** The current token, cleared after reading: each one is good for a single request. */
export function takeBotToken(): string | null {
  const value = token;
  if (value) setBotToken(null);
  return value;
}

export function onBotTokenChange(fn: (value: string | null) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function needsBotToken(url: string | undefined): boolean {
  if (!url) return false;
  const path = url.replace(/^https?:\/\/[^/]+/, '').replace(/^\/api\/v1/, '').split('?')[0];
  return (BOT_CHECK_PATHS as readonly string[]).includes(path);
}
