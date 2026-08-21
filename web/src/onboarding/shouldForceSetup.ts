import { isSetupWizardEnabled } from '@/config/features';
import type { Company, User } from '@/types/domain';

export function shouldForceSetup(
  user?: User | null,
  company?: Company | null,
): boolean {
  if (!isSetupWizardEnabled() || user?.role !== 'OWNER') return false;
  const status = company?.onboarding?.status;
  return status === 'NOT_STARTED' || status === 'IN_PROGRESS';
}
