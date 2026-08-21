import type { Company, RegistrationType } from '@/types/domain';

export function isTaxProfileComplete(company?: Company | null): boolean {
  if (!company) return false;
  if (company.registrationType === 'REGULAR') return Boolean(company.gstin?.trim());
  return Boolean(
    company.taxProfileConfirmedAt ||
      (company.onboarding?.taxDone &&
        (company.registrationType === 'UNREGISTERED' ||
          company.registrationType === 'COMPOSITION')),
  );
}

export function shopDetailsComplete(company?: Company | null): boolean {
  return Boolean(company?.address?.trim() && company?.state?.trim());
}

export function preferredInvoiceType(
  registrationType?: RegistrationType,
): 'NON_GST' | 'GST' {
  return registrationType === 'REGULAR' ? 'GST' : 'NON_GST';
}

export function firstBillHelpTextKey(registrationType?: RegistrationType): string {
  return registrationType === 'REGULAR'
    ? 'onboarding.stepInvoiceDescRegular'
    : 'onboarding.stepInvoiceDescBos';
}

export function companyStepIncompleteNeedsGst(company?: Company | null): boolean {
  return company?.registrationType === 'REGULAR' && !company.gstin?.trim();
}
