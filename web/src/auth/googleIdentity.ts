/** WP-ID5: load Google Identity Services once, only when a client id is configured. */

interface GoogleIdApi {
  accounts: {
    id: {
      initialize: (config: Record<string, unknown>) => void;
      renderButton: (el: HTMLElement, options: Record<string, unknown>) => void;
    };
  };
}

const SCRIPT_SRC = 'https://accounts.google.com/gsi/client';
let loading: Promise<GoogleIdApi | null> | null = null;

export function googleClientId(): string {
  return String(import.meta.env.VITE_GOOGLE_CLIENT_ID ?? '').trim();
}

export function loadGoogleIdentity(): Promise<GoogleIdApi | null> {
  if (typeof window === 'undefined' || !googleClientId()) return Promise.resolve(null);
  const existing = (window as unknown as { google?: GoogleIdApi }).google;
  if (existing?.accounts?.id) return Promise.resolve(existing);
  if (!loading) {
    loading = new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve((window as unknown as { google?: GoogleIdApi }).google ?? null);
      script.onerror = () => {
        loading = null;
        resolve(null);
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}
