export function trackOnboardingEvent(
  name: string,
  props?: Record<string, unknown>,
): void {
  try {
    if (import.meta.env.VITE_ONBOARDING_ANALYTICS === 'console' || import.meta.env.DEV) {
      console.info('[onboarding]', name, props);
    }
  } catch {
    // Analytics must never interrupt onboarding.
  }
  try {
    (
      window as Window & {
        bizboardAnalytics?: { track?: (event: string, data?: Record<string, unknown>) => void };
      }
    ).bizboardAnalytics?.track?.(name, props);
  } catch {
    // Third-party analytics are best effort.
  }
}
