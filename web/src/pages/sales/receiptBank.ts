import type { BankAccount } from '@/types/domain';

/** Payment modes whose money is deposited into a bank account (never cash or cheque). */
export const BANK_MODES = ['UPI', 'BANK', 'CARD'] as const;

/** The company's default bank, else its only active one. A cash box is never a bank. */
export function defaultBankFor(accounts: BankAccount[]): BankAccount | null {
  const banks = accounts.filter((a) => a.isActive !== false && a.accountType !== 'CASH_BOX');
  const preferred = banks.find((a) => a.isDefault);
  if (preferred) return preferred;
  return banks.length === 1 ? banks[0] : null;
}
