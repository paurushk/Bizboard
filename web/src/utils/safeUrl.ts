const SHARE_HOSTS = [
  'wa.me',
  'api.whatsapp.com',
] as const;

function hostAllowed(host: string, exact: string, suffix?: string): boolean {
  return host === exact || (suffix ? host.endsWith(suffix) : false);
}

export function isAllowedShareUrl(url: string): boolean {
  try {
    const u = new URL(url);
    if (u.protocol === 'javascript:') return false;
    if (u.protocol !== 'https:' && u.protocol !== 'http:') return false;
    const host = u.hostname.toLowerCase();
    return (
      SHARE_HOSTS.some((h) => host === h) ||
      host.endsWith('.whatsapp.com') ||
      host === 'localhost' ||
      host.endsWith('.bizboard.local')
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
  if (trimmed.toLowerCase().startsWith('javascript:')) return false;
  if (trimmed.toLowerCase().startsWith('upi:')) return true;
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) return true;
  try {
    const u = new URL(trimmed);
    if (u.protocol === 'javascript:') return false;
    if (u.protocol === 'upi:') return true;
    if (u.protocol !== 'https:' && u.protocol !== 'http:') return false;
    const host = u.hostname.toLowerCase();
    return (
      hostAllowed(host, 'rzp.io', '.rzp.io') ||
      hostAllowed(host, 'razorpay.com', '.razorpay.com') ||
      host === 'api.razorpay.com' ||
      host === 'localhost' ||
      host.endsWith('.bizboard.local')
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
