export const AMBIGUITY_MAP: Record<string, { label: string; intentId: string }[]> = {
  gst: [
    { label: 'Add or change GSTIN', intentId: 'add-gstin' },
    { label: 'Wrong tax on a bill', intentId: 'wrong-gst-on-invoice' },
    { label: 'Regular vs Composition vs Unregistered', intentId: 'registration-type' },
  ],
  invoice: [
    { label: 'Create / Complete a bill', intentId: 'cannot-complete-invoice' },
    { label: 'Correct a done bill', intentId: 'edit-completed-invoice' },
    { label: 'Share or PDF', intentId: 'pdf-or-share-unavailable' },
    { label: 'Understand tax on a bill', intentId: 'wrong-gst-on-invoice' },
  ],
  'invoice problem': [
    { label: 'Create / Complete a bill', intentId: 'cannot-complete-invoice' },
    { label: 'Correct a done bill', intentId: 'edit-completed-invoice' },
    { label: 'Share or PDF', intentId: 'pdf-or-share-unavailable' },
    { label: 'Understand tax', intentId: 'wrong-gst-on-invoice' },
  ],
  'stock issue': [
    { label: 'Cannot sell / add item', intentId: 'sell-blocked' },
    { label: 'Stock is in another Godown', intentId: 'stock-in-another-godown' },
    { label: 'Units and conversion', intentId: 'unit-conversion-rate' },
  ],
  stock: [
    { label: 'Cannot sell / add item', intentId: 'sell-blocked' },
    { label: 'Stock is in another Godown', intentId: 'stock-in-another-godown' },
  ],
  payment: [
    { label: 'Receipt will not match a bill', intentId: 'payment-wont-allocate' },
    { label: 'Your login cannot do this', intentId: 'login-cant-do-this' },
  ],
  import: [{ label: 'Excel / Tally red rows', intentId: 'import-row-errors' }],
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Whole-phrase match so "gst" does not fire inside "gstin". */
export function ambiguityKeyMatches(query: string, key: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return false;
  if (needle === key) return true;
  return new RegExp(`(?:^|\\s)${escapeRegExp(key)}(?:\\s|$)`).test(needle);
}

export function ambiguityChips(query: string): { id: string; label: string; intentId: string }[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [];
  const keys = Object.keys(AMBIGUITY_MAP).sort((a, b) => b.length - a.length);
  for (const key of keys) {
    if (ambiguityKeyMatches(needle, key)) {
      return AMBIGUITY_MAP[key].map((c) => ({
        id: `${key}:${c.intentId}`,
        label: c.label,
        intentId: c.intentId,
      }));
    }
  }
  return [];
}

/** Exact map key only — used to force the clarifier before scoring. */
export function isAmbiguousKey(query: string): boolean {
  const needle = query.trim().toLowerCase();
  return Object.keys(AMBIGUITY_MAP).some((key) => needle === key);
}
