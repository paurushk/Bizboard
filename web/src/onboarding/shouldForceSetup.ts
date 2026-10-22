import { isSetupWizardEnabled } from '@/config/features';
import type { Company, User } from '@/types/domain';

export function shouldForceSetup(
  user?: User | null,
  company?: Company | null,
): boolean {
  if (!isSetupWizardEnabled() || user?.role !== 'OWNER') return false;
  const onboarding = company?.onboarding;
  // ONB-CR-001: a draft first bill is waiting for review -- the dashboard checklist takes over from
  // here; sending the owner back to the wizard would only offer to create another draft.
  if (onboarding?.step === 'first_bill' && onboarding.firstBillDraftId) return false;
  const status = onboarding?.status;
  return status === 'NOT_STARTED' || status === 'IN_PROGRESS';
}
