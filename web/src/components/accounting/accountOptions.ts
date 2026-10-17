import type { AccountingAccount } from '@/types/domain';

export function accountLabel(account: Pick<AccountingAccount, 'code' | 'name'>): string {
  return `${account.code} — ${account.name}`;
}

/** Accounts a new posting may use: inactive ones are hidden unless the caller asks for them (ACS-11). */
export function selectableAccounts(
  accounts: AccountingAccount[] | undefined,
  { allowInactive = false, types }: { allowInactive?: boolean; types?: string[] } = {},
): AccountingAccount[] {
  return (accounts ?? []).filter(
    (a) => (allowInactive || a.isActive !== false) && (!types || types.includes(a.type)),
  );
}
