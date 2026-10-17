import { toNumber } from '@/utils/money';

/** A stock-count line as the API returns it (camel-cased). */
export interface CountLine {
  id?: number;
  product?: number;
  productName?: string;
  productSku?: string;
  productBarcode?: string | null;
  batchNo?: string | null;
  systemQty?: string | number | null;
  countedQty?: string | number | null;
  variance?: string | number | null;
  varianceValueEstimate?: string | null;
  needsRecheck?: boolean;
  skipped?: boolean;
  driftSkipped?: boolean;
  /** Bumped by the server on every save of the line; sent back so a stale save is refused. */
  version?: number;
  /** The counter confirmed this line with "count equals system" instead of counting it. */
  filledFromSystem?: boolean;
}

const idKey = (line: CountLine) => String(line.id);

/** What the counter sees in the box: what they typed, else what is saved. */
export function effectiveCounted(line: CountLine, typed: Record<string, string>): string {
  const mine = typed[idKey(line)];
  if (mine !== undefined) return mine;
  return line.countedQty == null ? '' : String(line.countedQty);
}

export function effectiveSkipped(line: CountLine, skipped: Record<string, boolean>): boolean {
  const mine = skipped[idKey(line)];
  return mine !== undefined ? mine : Boolean(line.skipped);
}

/** A line that still needs a number or a decision to skip it. */
export function lineIsOpen(line: CountLine, typed: Record<string, string>, skipped: Record<string, boolean>): boolean {
  return !effectiveSkipped(line, skipped) && effectiveCounted(line, typed).trim() === '';
}

export function openLineCount(lines: CountLine[], typed: Record<string, string>, skipped: Record<string, boolean>): number {
  return lines.filter((line) => lineIsOpen(line, typed, skipped)).length;
}

/** Anything typed, skipped or un-skipped that is not saved yet (so closing would lose it). */
export function hasUnsavedCounts(
  lines: CountLine[],
  typed: Record<string, string>,
  skipped: Record<string, boolean>,
): boolean {
  return lines.some((line) => {
    const saved = line.countedQty == null ? '' : String(line.countedQty);
    const typedValue = typed[idKey(line)];
    const countChanged = typedValue !== undefined && typedValue.trim() !== saved.trim();
    const skipChanged = skipped[idKey(line)] !== undefined && skipped[idKey(line)] !== Boolean(line.skipped);
    return countChanged || skipChanged;
  });
}

export interface ReviewSummary {
  /** Lines whose count differs from the system quantity. */
  changed: number;
  /** Total worth of surplus, at purchase price. */
  gain: number;
  /** Total worth of shortage, as a positive number. */
  loss: number;
  /** Lines the counter must tick as rechecked before posting. */
  recheck: number;
  skipped: number;
}

export function summarizeReview(lines: CountLine[]): ReviewSummary {
  const out: ReviewSummary = { changed: 0, gain: 0, loss: 0, recheck: 0, skipped: 0 };
  for (const line of lines) {
    if (line.skipped) {
      out.skipped += 1;
      continue;
    }
    if (line.variance == null || toNumber(line.variance) === 0) continue;
    out.changed += 1;
    const value = toNumber(line.varianceValueEstimate);
    if (value >= 0) out.gain += value;
    else out.loss += -value;
    if (line.needsRecheck) out.recheck += 1;
  }
  return out;
}

/** Posting is allowed once every flagged line has been ticked as rechecked. */
export function canPostReview(lines: CountLine[], rechecked: Record<string, boolean>): boolean {
  return lines.every((line) => !line.needsRecheck || line.skipped || rechecked[idKey(line)]);
}

/**
 * "Count equals system": types the system quantity into every line that is still open. Only
 * possible where the system quantity is visible (a blind count hides it, on purpose).
 */
export function fillWithSystemQty(
  lines: CountLine[],
  typed: Record<string, string>,
  skipped: Record<string, boolean>,
): Record<string, string> {
  const next = { ...typed };
  for (const line of lines) {
    if (!lineIsOpen(line, typed, skipped) || line.systemQty == null) continue;
    next[idKey(line)] = String(line.systemQty);
  }
  return next;
}

/** Same as fillWithSystemQty, and says which lines it filled (they are marked as not counted). */
export function fillWithSystemQtyIds(
  lines: CountLine[],
  typed: Record<string, string>,
  skipped: Record<string, boolean>,
): { typed: Record<string, string>; ids: string[] } {
  const next = fillWithSystemQty(lines, typed, skipped);
  return { typed: next, ids: Object.keys(next).filter((key) => next[key] !== typed[key]) };
}

/** Lines changed on this screen and not saved: the only ones a save should send. */
export function changedLines(
  lines: CountLine[],
  typed: Record<string, string>,
  skipped: Record<string, boolean>,
  filled: Record<string, boolean>,
): CountLine[] {
  return lines.filter((line) => {
    const key = idKey(line);
    const saved = line.countedQty == null ? '' : String(line.countedQty);
    const typedValue = typed[key];
    const countChanged = typedValue !== undefined && typedValue.trim() !== saved.trim();
    const skipChanged = skipped[key] !== undefined && skipped[key] !== Boolean(line.skipped);
    const fillChanged = filled[key] !== undefined && filled[key] !== Boolean(line.filledFromSystem);
    return countChanged || skipChanged || fillChanged;
  });
}

/** Open lines that "count equals system" could fill. */
export function fillableLineCount(lines: CountLine[], typed: Record<string, string>, skipped: Record<string, boolean>): number {
  return lines.filter((line) => lineIsOpen(line, typed, skipped) && line.systemQty != null).length;
}

/** The lines a scanned code could mean: the item's lines that are still being counted (one per lot). */
export function scanCandidates(lines: CountLine[], skipped: Record<string, boolean>, code: string): CountLine[] {
  const wanted = code.trim().toLowerCase();
  if (!wanted) return [];
  return lines.filter(
    (line) =>
      !effectiveSkipped(line, skipped) &&
      [line.productBarcode, line.productSku].some((value) => value && String(value).trim().toLowerCase() === wanted),
  );
}

/** Count one unit on a chosen line. */
export function countOneOn(line: CountLine, typed: Record<string, string>): Record<string, string> {
  const current = toNumber(effectiveCounted(line, typed) || 0);
  return { ...typed, [idKey(line)]: String(current + 1) };
}

/**
 * A scan counts one unit. Matches the item's barcode or code (no case, no spaces); of several
 * lots of one item it takes the first line still being counted. Returns null for an unknown code.
 */
export function applyScan(
  lines: CountLine[],
  typed: Record<string, string>,
  skipped: Record<string, boolean>,
  code: string,
): { typed: Record<string, string>; line: CountLine } | null {
  const wanted = code.trim().toLowerCase();
  if (!wanted) return null;
  const matches = lines.filter(
    (line) =>
      !effectiveSkipped(line, skipped) &&
      [line.productBarcode, line.productSku].some((value) => value && String(value).trim().toLowerCase() === wanted),
  );
  if (matches.length === 0) return null;
  const line = matches[0];
  const current = toNumber(effectiveCounted(line, typed) || 0);
  return { typed: { ...typed, [idKey(line)]: String(current + 1) }, line };
}
