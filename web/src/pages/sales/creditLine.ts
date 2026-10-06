export type CreditLineView = {
  severity: 'info' | 'warning' | 'error';
  outstanding: number;
  limit: number;
  available: number;
};

/** Figures shown under a party with a credit limit. Available is limit minus what they already owe. */
export function creditLineView(input: {
  limit: number;
  outstanding: number;
  billTotal: number;
}): CreditLineView | null {
  if (!(input.limit > 0)) return null;
  const outstanding = input.outstanding;
  const limit = input.limit;
  const exceeded = outstanding + input.billTotal > limit + 1e-9;
  // Warn on exposure (what they owe plus this bill), not owed-so-far: a bill that takes a
  // customer from 70% to 99% of the limit must not look the same as a small one.
  const amber = !exceeded && outstanding + input.billTotal >= limit * 0.8 - 1e-9;
  return {
    severity: exceeded ? 'error' : amber ? 'warning' : 'info',
    outstanding,
    limit,
    available: limit - outstanding,
  };
}
