/** Customer portal debug link hint — same posture as loginOtp.ts's formatOtpHint,
 * kept off production builds (only DEV + a backend-echoed debugToken renders it). */

export function formatPortalDebugHint(
  res: { detail: string; debugToken?: string },
  isDev: boolean = import.meta.env.DEV,
): string | null {
  if (isDev && res.debugToken) {
    return `Dev portal link: /portal/${res.debugToken}`;
  }
  return null;
}
