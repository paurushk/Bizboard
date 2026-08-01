/** OTP login helpers — keep debug codes off production UI (BUG-628 / P0-108). */

export function isOtpLoginEnabled(
  isDev: boolean = import.meta.env.DEV,
  enableFlag: string | undefined = import.meta.env.VITE_ENABLE_OTP,
): boolean {
  // Production builds hide OTP unless explicitly enabled (SMS configured).
  return Boolean(isDev) || enableFlag === 'true';
}

export function formatOtpHint(
  res: { detail: string; debugCode?: string },
  isDev: boolean = import.meta.env.DEV,
): string {
  if (isDev && res.debugCode) {
    return `Dev OTP: ${res.debugCode}`;
  }
  return res.detail;
}
