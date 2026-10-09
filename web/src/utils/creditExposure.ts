/** Client credit gate. `outstanding` is the server credit exposure (outstanding minus advances).
 * A completed invoice being amended is already inside that figure, so its open balance is removed first.
 */
export function projectedCreditExposure(args: {
  outstanding: number;
  draftTotal: number;
  alreadyPosted?: number;
}): number {
  const posted = Math.max(0, args.alreadyPosted ?? 0);
  const base = Math.max(0, args.outstanding - posted);
  return base + Math.max(0, args.draftTotal);
}

export function creditLimitExceeded(args: {
  limit: number;
  outstanding: number;
  draftTotal: number;
  alreadyPosted?: number;
}): boolean {
  if (!(args.limit > 0)) return false;
  return projectedCreditExposure(args) > args.limit + 1e-9;
}
