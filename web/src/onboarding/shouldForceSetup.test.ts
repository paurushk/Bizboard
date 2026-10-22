import { describe, expect, it, vi } from 'vitest';
import { shouldForceSetup } from '@/onboarding/shouldForceSetup';
import type { Company, User } from '@/types/domain';

vi.mock('@/config/features', () => ({ isSetupWizardEnabled: () => true }));

const owner = { id: 1, role: 'OWNER' } as unknown as User;
const companyWith = (onboarding: Record<string, unknown>) => ({ onboarding } as unknown as Company);

describe('shouldForceSetup', () => {
  it('sends an owner with setup in progress to the wizard', () => {
    expect(shouldForceSetup(owner, companyWith({ status: 'IN_PROGRESS', step: 'catalog' }))).toBe(true);
  });

  it('ONB-CR-001: stops once the wizard has saved a draft first bill', () => {
    expect(shouldForceSetup(owner, companyWith({ status: 'IN_PROGRESS', step: 'first_bill', firstBillDraftId: 5 }))).toBe(false);
  });

  it('still forces setup at the first-bill step when no draft exists yet', () => {
    expect(shouldForceSetup(owner, companyWith({ status: 'IN_PROGRESS', step: 'first_bill', firstBillDraftId: null }))).toBe(true);
  });

  it('a draft does not excuse an earlier unfinished step', () => {
    expect(shouldForceSetup(owner, companyWith({ status: 'IN_PROGRESS', step: 'tax', firstBillDraftId: 5 }))).toBe(true);
  });

  it('never forces a non-owner', () => {
    const staff = { id: 2, role: 'STAFF' } as unknown as User;
    expect(shouldForceSetup(staff, companyWith({ status: 'NOT_STARTED', step: 'tax' }))).toBe(false);
  });
});
