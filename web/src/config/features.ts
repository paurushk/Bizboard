/**

 * Frontend feature flags for pilot honesty.

 * When VITE_PILOT_ADVANCED=true, GSTR / AI / Tally / e-invoice submit are

 * treated as enabled at call sites for local full demos.

 * BB-000223: never honor PILOT_ADVANCED in production builds.

 * BB-000741: accounting/AI/GSTR/Tally honor runtime flags like POS/mfg.

 */



import { getCachedFeatureFlags, isRuntimeFlagEnabled } from '@/config/featureFlags';



if (import.meta.env.PROD && import.meta.env.VITE_PILOT_ADVANCED === 'true') {

  throw new Error('VITE_PILOT_ADVANCED must not be enabled for production builds');

}



const pilotAdvanced =

  !import.meta.env.PROD && import.meta.env.VITE_PILOT_ADVANCED === 'true';



export const features = {

  gstrReports: import.meta.env.VITE_ENABLE_GSTR === 'true',

  einvoiceSubmit: import.meta.env.VITE_ENABLE_EINVOICE_SUBMIT === 'true',

  /** BB-000344: off by default; company.accountingEnabled still required when on. */

  accounting: import.meta.env.VITE_ENABLE_ACCOUNTING === 'true',

  aiInsights: import.meta.env.VITE_ENABLE_AI === 'true',

  tally: import.meta.env.VITE_ENABLE_TALLY === 'true',

  /** Wave 17D — MVP modules (not full ERP). Prefer runtime flags when available. */

  manufacturing: import.meta.env.VITE_ENABLE_MANUFACTURING === 'true',

  payroll: import.meta.env.VITE_ENABLE_PAYROLL === 'true',

  crm: import.meta.env.VITE_ENABLE_CRM === 'true',

  /** Wave 18D — counter POS MVP (not full retail suite). */

  pos: import.meta.env.VITE_ENABLE_POS === 'true',

  tds: import.meta.env.VITE_ENABLE_TDS === 'true',

  setupWizard: import.meta.env.VITE_ENABLE_SETUP_WIZARD === 'true',

  advancedPilot: pilotAdvanced,

};



/**
 * BB-000751 fix: once the per-company runtime flags have loaded, they are the
 * sole authority (a module a company's plan/admin has turned off must not be
 * re-enabled just because the bundle was baked with the build-time default
 * on) — the build-time VITE_ENABLE_* value is only a fallback shown before
 * the runtime flags have loaded, to avoid a flash of the wrong state.
 * advancedPilot (dev-only, never true in production builds) still force-
 * enables everything for local full demos regardless of runtime state.
 */
function resolveModuleFlag(buildDefault: boolean, runtimeKey: string): boolean {
  if (features.advancedPilot) return true;
  const cached = getCachedFeatureFlags();
  if (cached) return isRuntimeFlagEnabled(runtimeKey);
  return buildDefault;
}

/** Off until runtime flags load so Manufacturing/Payroll/CRM do not flash then hide. */
function resolveOptionalModuleFlag(_buildDefault: boolean, runtimeKey: string): boolean {
  if (features.advancedPilot) return true;
  const cached = getCachedFeatureFlags();
  if (!cached) return false;
  return isRuntimeFlagEnabled(runtimeKey);
}

export function isGstrReportsEnabled(): boolean {

  return resolveModuleFlag(features.gstrReports, 'ENABLE_GSTR');

}



export function isAiInsightsEnabled(): boolean {

  return resolveModuleFlag(features.aiInsights, 'ENABLE_AI');

}



export function isTallyEnabled(): boolean {

  return resolveModuleFlag(features.tally, 'ENABLE_TALLY');

}



export function isAccountingFeatureEnabled(): boolean {

  return resolveModuleFlag(features.accounting, 'ENABLE_ACCOUNTING');

}



export function isEinvoiceSubmitEnabled(): boolean {

  return features.einvoiceSubmit || features.advancedPilot;

}

export function isEwaySubmitEnabled(): boolean {
  if (features.advancedPilot) return true;
  return isRuntimeFlagEnabled('ENABLE_EWAY') || features.einvoiceSubmit;
}



export function isManufacturingEnabled(): boolean {

  return resolveOptionalModuleFlag(features.manufacturing, 'ENABLE_MANUFACTURING');

}



export function isPayrollEnabled(): boolean {

  return resolveOptionalModuleFlag(features.payroll, 'ENABLE_PAYROLL');

}



export function isCrmEnabled(): boolean {

  return resolveOptionalModuleFlag(features.crm, 'ENABLE_CRM');

}



export function isPosEnabled(): boolean {

  return resolveModuleFlag(features.pos, 'ENABLE_POS');

}

export function isTdsEnabled(): boolean {

  return resolveModuleFlag(features.tds, 'ENABLE_TDS');

}

export function isSetupWizardEnabled(): boolean {
  return resolveModuleFlag(features.setupWizard, 'ENABLE_SETUP_WIZARD');
}

/** Item custom fields utilization (columns, picker, filters). Default ON; company JSON can kill-switch. */
export function isItemCustomFieldsV2Enabled(): boolean {
  if (features.advancedPilot) return true;
  const cached = getCachedFeatureFlags();
  if (!cached) return true;
  const value =
    cached.item_custom_fields_v2 ?? cached.itemCustomFieldsV2 ?? cached.ITEM_CUSTOM_FIELDS_V2;
  if (value === undefined) return true;
  return Boolean(value);
}

/** Help v2 shell + Why? / HelpHint / prevention / search hits. Pre-GA default off. */
export function isHelpV2Enabled(): boolean {
  try {
    // Playwright / local only — never honor this key in a production bundle.
    if (
      import.meta.env.DEV &&
      typeof sessionStorage !== 'undefined' &&
      sessionStorage.getItem('bizboard:e2eHelpV2') === '1'
    ) {
      return true;
    }
  } catch {
    // ignore
  }
  if (features.advancedPilot) return true;
  const preload = import.meta.env.VITE_HELP_V2 === 'true';
  const cached = getCachedFeatureFlags();
  if (!cached) return preload;
  const value = cached.helpV2 ?? cached.help_v2 ?? cached.HELP_V2;
  if (value === undefined) return preload;
  return Boolean(value);
}


