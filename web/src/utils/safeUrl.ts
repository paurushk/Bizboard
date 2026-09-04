import { isValidUpiVpa } from '@/utils/gst';

const SHARE_HOSTS = [
  'wa.me',
  'api.whatsapp.com',
] as const;

// F1-010: only trust http: / localhost / *.bizboard.local in a dev build.
const DEV = typeof import.meta !== 'undefined' && Boolean(import.meta.env?.DEV);

function hostAllowed(host: string, exact: string, suffix?: string): boolean {
  return host === exact || (suffix ? host.endsWith(suffix) : false);
}

/** A `upi:` intent is safe only when it names a plausible payee VPA. */
function isSafeUpiIntent(raw: string): boolean {
  const q = raw.indexOf('?');
  if (q < 0) return false;
  try {
    return isValidUpiVpa(new URLSearchParams(raw.slice(q + 1)).get('pa') || '');
  } catch {
    return false;
  }
}

export function isAllowedShareUrl(url: string): boolean {
  try {
    const u = new URL(url);
    if (u.protocol === 'javascript:') return false;
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && DEV)) return false;
    const host = u.hostname.toLowerCase();
    return (
      SHARE_HOSTS.some((h) => host === h) ||
      host.endsWith('.whatsapp.com') ||
      (DEV && (host === 'localhost' || host.endsWith('.bizboard.local')))
    );
  } catch {
    return false;
  }
}

/**
 * BB-000211: allowlist for payment provider short URLs and UPI intents.
 * Relative same-app paths (e.g. /pay/:token) are allowed.
 */
export function isAllowedPaymentUrl(url: string): boolean {
  const trimmed = (url || '').trim();
  if (!trimmed) return false;
  const lower = trimmed.toLowerCase();
  if (lower.startsWith('javascript:')) return false;
  // F1-010: a upi: intent must carry a plausible payee VPA (was blindly true).
  if (lower.startsWith('upi:')) return isSafeUpiIntent(trimmed);
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return true;
  try {
    const u = new URL(trimmed);
    if (u.protocol === 'javascript:') return false;
    if (u.protocol === 'upi:') return isSafeUpiIntent(trimmed);
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && DEV)) return false;
    const host = u.hostname.toLowerCase();
    return (
      hostAllowed(host, 'rzp.io', '.rzp.io') ||
      hostAllowed(host, 'razorpay.com', '.razorpay.com') ||
      hostAllowed(host, 'cashfree.com', '.cashfree.com') ||
      hostAllowed(host, 'cashfree.in', '.cashfree.in') ||
      hostAllowed(host, 'payu.in', '.payu.in') ||
      hostAllowed(host, 'payu.com', '.payu.com') ||
      hostAllowed(host, 'phonepe.com', '.phonepe.com') ||
      hostAllowed(host, 'paytm.com', '.paytm.com') ||
      hostAllowed(host, 'easebuzz.in', '.easebuzz.in') ||
      host === 'api.razorpay.com' ||
      (DEV && (host === 'localhost' || host.endsWith('.bizboard.local')))
    );
  } catch {
    return false;
  }
}

export function openShareUrl(url: string) {
  if (!isAllowedShareUrl(url)) throw new Error('Blocked share URL');
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function openPaymentUrl(url: string) {
  if (!isAllowedPaymentUrl(url)) throw new Error('Blocked payment URL');
  window.open(url, '_blank', 'noopener,noreferrer');
}

/** Return href only when allowlisted; otherwise null (BB-000211). */
export function safePaymentHref(url: string): string | null {
  const trimmed = (url || '').trim();
  if (!trimmed) return null;
  return isAllowedPaymentUrl(trimmed) ? trimmed : null;
}

/**
 * F1-011 / F3-032: a value is safe to hand to react-router `to=` only if it is
 * an in-app relative path. Backend- and LLM-supplied hrefs must go through this.
 */
export function safeAppPath(path: unknown, fallback = '/'): string {
  const p = typeof path === 'string' ? path.trim() : '';
  const BACKSLASH = String.fromCharCode(92);
  if (!p || p[0] !== '/' || p[1] === '/' || p[1] === BACKSLASH) return fallback;
  if (/\s/.test(p) || p.includes(BACKSLASH)) return fallback;
  for (let i = 0; i < p.length; i += 1) {
    const c = p.charCodeAt(i);
    if (c < 32 || c === 127) return fallback;
  }
  return p;
}
