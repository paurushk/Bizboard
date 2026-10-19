import { toNumber } from '@/utils/money';

type Rec = Record<string, unknown>;

function pick(obj: unknown, ...keys: string[]): unknown {
  if (!obj || typeof obj !== 'object') return undefined;
  for (const k of keys) {
    const v = (obj as Rec)[k];
    if (v !== undefined && v !== null) return v;
  }
  return undefined;
}

function sumHeads(block: unknown): number {
  return (
    toNumber(pick(block, 'igst') as string | number | undefined) +
    toNumber(pick(block, 'cgst') as string | number | undefined) +
    toNumber(pick(block, 'sgst') as string | number | undefined) +
    toNumber(pick(block, 'cess') as string | number | undefined)
  );
}

export interface Flagged {
  count: number;
  total: number;
  igst: number;
  cgst: number;
  sgst: number;
  cess: number;
}

function flagged(block: unknown): Flagged {
  return {
    count: Number(pick(block, 'count') ?? 0),
    total: toNumber(pick(block, 'totalTax', 'total_tax') as string | number | undefined),
    igst: toNumber(pick(block, 'igst') as string | number | undefined),
    cgst: toNumber(pick(block, 'cgst') as string | number | undefined),
    sgst: toNumber(pick(block, 'sgst') as string | number | undefined),
    cess: toNumber(pick(block, 'cess') as string | number | undefined),
  };
}

export interface Gstr3bSummary {
  outwardTax: number;
  rcmTax: number;
  /** ITC that is safe to claim now (the lower of books and matched 2B), 0 when there is no 2B. */
  claimableItc: number;
  claimBasis: string;
  /** The backend's own net payable. Null when the payload does not carry it. */
  netPayable: number | null;
  /** Worksheet figure: never below zero. */
  payableToShow: number;
  carryForward: number;
  booksItc: number;
  hasMatched2b: boolean;
  unreviewedItc: number;
  rcmProvisionalItc: number;
  importItc: number;
  reversed: Flagged;
  ineligible: Flagged;
  needsCaConfirmation: boolean;
  gstr2bFlaggedCount: number;
}

/**
 * RPT-07: read the GSTR-3B figures from the payload instead of re-deriving them in the browser.
 * The backend's net payable already includes reverse-charge tax and cess; a client-side
 * "tax minus ITC" left both out.
 */
export function summarizeGstr3b(data: Rec | undefined): Gstr3bSummary {
  const outward = pick(data, 'outwardSupplies', 'outward_supplies');
  const inward = pick(data, 'inwardSupplies', 'inward_supplies');
  const rcm = pick(inward, 'reverseCharge', 'reverse_charge');
  const itc = pick(data, 'itc');
  const rec = pick(itc, 'recommendedClaimable', 'recommended_claimable');
  const payable = pick(data, 'taxPayableSummary', 'tax_payable_summary');
  const revInel = pick(itc, 'reversedIneligible', 'reversed_ineligible');
  const hint = pick(payable, 'netPayableHint', 'net_payable_hint');
  const netPayable = hint === undefined ? null : toNumber(hint as string | number);
  const basis = String(pick(rec, 'basis') ?? '');
  return {
    outwardTax: sumHeads(outward),
    rcmTax: sumHeads(rcm),
    claimableItc: sumHeads(rec),
    claimBasis: basis,
    netPayable,
    payableToShow: netPayable === null ? 0 : Math.max(0, netPayable),
    carryForward: netPayable !== null && netPayable < 0 ? -netPayable : 0,
    booksItc: sumHeads(pick(itc, 'booksItc', 'books_itc')),
    hasMatched2b: basis === 'min(books, gstr2b_matched)',
    unreviewedItc: sumHeads(pick(itc, 'unreviewedItc', 'unreviewed_itc')),
    rcmProvisionalItc: toNumber(pick(pick(itc, 'rcmProvisional', 'rcm_provisional'), 'totalTax', 'total_tax') as string | number | undefined),
    importItc: toNumber(pick(pick(itc, 'importItc', 'import_itc'), 'totalTax', 'total_tax') as string | number | undefined),
    reversed: flagged(pick(revInel, 'reversed')),
    ineligible: flagged(pick(revInel, 'ineligible')),
    needsCaConfirmation: pick(revInel, 'needsCaConfirmation', 'needs_ca_confirmation') === true,
    gstr2bFlaggedCount: Number(pick(pick(revInel, 'gstr2bFlagged', 'gstr2b_flagged'), 'count') ?? 0),
  };
}
