import { t, tOptional } from '@/i18n';
import type { AttentionRow } from '@/types/domain';

type Params = Record<string, unknown> | undefined;

/** A signal inside a merged customer row, with its own values. */
interface Signal {
  code: string;
  params?: Record<string, unknown>;
  title: string;
  reason: string;
}

type TextRow = Pick<AttentionRow, 'code' | 'params' | 'title' | 'reason'>;

/** Look a key up; null when the catalogue has no entry or the template lacks values it needs. */
function lookup(key: string, params?: Record<string, string | number>): string | null {
  const value = tOptional(key, params);
  return value !== null && /\{\w+\}/.test(value) ? null : value;
}

function scalarParams(params: Params): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params ?? {})) {
    if (typeof v === 'string' || typeof v === 'number') out[k] = v;
  }
  // The server sends codes for these; show them in the user's language.
  if (typeof out.status === 'string') out.status = tOptional(`attention.collectionStatus.${out.status}`) ?? out.status;
  if (typeof out.step === 'string') out.step = tOptional(`attention.collectionStep.${out.step}`) ?? out.step;
  return out;
}

function signalsOf(row: Pick<AttentionRow, 'params'>): Signal[] {
  const raw = (row.params as { signals?: unknown } | undefined)?.signals;
  return Array.isArray(raw) ? (raw as Signal[]) : [];
}

/** Try `CODE.<variant>.part` first, then `CODE.part`. */
function translate(row: TextRow, part: 'title' | 'reason'): string | null {
  const params = row.params ?? {};
  // No values from the server means it did not structure this row: show its own text.
  if (Object.keys(params).length === 0) return null;
  const variantKey = part === 'title' ? 'titleVariant' : 'variant';
  const variant = typeof params[variantKey] === 'string'
    ? (params[variantKey] as string)
    : typeof params.variant === 'string' ? (params.variant as string) : '';
  const values = scalarParams(params);
  const tries = variant
    ? [`attention.rows.${row.code}.${variant}.${part}`, `attention.rows.${row.code}.${part}`]
    : [`attention.rows.${row.code}.${part}`];
  for (const key of tries) {
    const found = lookup(key, values);
    if (found !== null) return found;
  }
  return null;
}

/** Title in the user's language when the row carries the values to build it, else the server text. */
export function attentionTitle(row: TextRow): string {
  if (row.code === 'AR_CUSTOMER') {
    const signals = signalsOf(row);
    if (signals.length === 1) return attentionTitle({ ...signals[0], params: signals[0].params });
    if (signals.length > 1) return translate(row, 'title') ?? row.title;
  }
  return translate(row, 'title') ?? row.title;
}

export function attentionReason(row: TextRow): string {
  if (row.code === 'AR_CUSTOMER') {
    const signals = signalsOf(row);
    if (signals.length > 0) {
      const parts: string[] = [];
      for (const signal of signals) {
        const text = attentionReason(signal);
        if (text && !parts.includes(text)) parts.push(text);
      }
      return parts.join(' ');
    }
  }
  const translated = translate(row, 'reason');
  if (translated !== null) return translated;
  // Legacy alerts use one sentence for both; translate that sentence from the title template.
  if (row.reason === row.title) return translate(row, 'title') ?? row.reason;
  return row.reason;
}

function slug(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

/** The Fix button text: a translation for the known labels, the server text for the rest. */
export function attentionActionLabel(row: Pick<AttentionRow, 'actionLabel'>): string {
  const label = row.actionLabel || '';
  if (!label) return t('attention.fix');
  return lookup(`attention.actions.${slug(label)}`) ?? label;
}
