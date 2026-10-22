/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_USE_MOCKS: string;
  readonly VITE_ENABLE_GSTR: string;
  readonly VITE_ENABLE_AI: string;
  readonly VITE_ENABLE_TALLY: string;
  /** WP-AB2: Cloudflare Turnstile site key; empty = no bot-check widget. */
  readonly VITE_TURNSTILE_SITE_KEY?: string;
  /** WP-ID5: Google OAuth web client id; blank hides Sign in with Google. */
  readonly VITE_GOOGLE_CLIENT_ID?: string;
  readonly VITE_ENABLE_EINVOICE_SUBMIT: string;
  readonly VITE_ENABLE_ACCOUNTING: string;
  readonly VITE_PILOT_ADVANCED: string;
  readonly VITE_ENABLE_OTP: string;
  readonly VITE_ENABLE_MANUFACTURING: string;
  readonly VITE_ENABLE_PAYROLL: string;
  readonly VITE_ENABLE_CRM: string;
  readonly VITE_ENABLE_POS: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
