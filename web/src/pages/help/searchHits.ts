import type { SearchResult } from '@/types/domain';
import { resolveHelpQuery } from './resolver';

/** Question-like opener, including Hinglish (HR-2.8). */
export const HELP_QUESTION_RE = /^(how|why|what|can|kaise|kyu|kyun|kya|kaha)\b/i;

export function isNearExactSkuOrParty(hits: SearchResult[], query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle.length < 2) return false;
  const compact = needle.replace(/\s+/g, '');
  return hits.some((hit) => {
    if (hit.type !== 'product' && hit.type !== 'customer' && hit.type !== 'supplier') return false;
    const title = hit.title.toLowerCase();
    const subtitle = (hit.subtitle ?? '').toLowerCase();
    return (
      title === needle ||
      subtitle === needle ||
      title.replace(/\s+/g, '') === compact ||
      subtitle.replace(/\s+/g, '') === compact
    );
  });
}

/** Up to 3 Help hits below records. Empty when a SKU/party is an exact match. */
export function buildHelpSearchHits(query: string, recordHits: SearchResult[]): SearchResult[] {
  const trimmed = query.trim();
  if (trimmed.length < 2) return [];
  if (isNearExactSkuOrParty(recordHits, trimmed)) return [];
  const resolved = resolveHelpQuery(trimmed);
  const questionLike = HELP_QUESTION_RE.test(trimmed);
  const resolverOk =
    resolved.state === 'confident' ||
    resolved.state === 'ambiguous' ||
    resolved.state === 'diagnostic';
  if (!questionLike && !resolverOk) return [];
  const intents = resolved.intent
    ? [resolved.intent, ...resolved.hits.map((h) => h.intent).filter((i) => i.intentId !== resolved.intent?.intentId)]
    : resolved.hits.map((h) => h.intent);
  const unique = intents.filter((intent, i, arr) => arr.findIndex((x) => x.intentId === intent.intentId) === i);
  return unique.slice(0, 3).map((intent) => ({
    id: intent.intentId,
    type: 'help' as const,
    title: intent.canonicalQuestion,
    subtitle: intent.category,
    path: `/help?intent=${encodeURIComponent(intent.intentId)}&source=search`,
  }));
}
