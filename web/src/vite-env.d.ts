/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_USE_MOCKS: string;
  readonly VITE_ENABLE_GSTR: string;
  readonly VITE_ENABLE_AI: string;
  readonly VITE_ENABLE_TALLY: string;
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
