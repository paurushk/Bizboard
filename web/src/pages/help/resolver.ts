import { ambiguityChips, isAmbiguousKey } from './ambiguityMap';
import { HELP_INTENTS, getHelpIntent } from './intents';
import { expand } from './synonyms';
import type { HelpIntent, ResolverHit, ResolverResult } from './types';

const STOP = new Set(['a', 'an', 'the', 'to', 'of', 'in', 'on', 'for', 'my', 'i', 'do', 'me', 'please']);
const CACHE_MAX = 64;
const queryCache = new Map<string, ResolverResult>();

export function tokenize(raw: string): string[] {
  return raw
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s']+/gu, ' ')
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0 && !STOP.has(t));
}

/** Single-word tokens plus expansions of 2–4 word n-grams ("nahi ban raha"). */
export function expandedQueryTokens(raw: string): string[] {
  const base = tokenize(raw);
  const extra: string[] = [];
  const maxN = Math.min(4, base.length);
  for (let n = 2; n <= maxN; n += 1) {
    for (let i = 0; i + n <= base.length; i += 1) {
      const gram = base.slice(i, i + n).join(' ');
      for (const w of expand(gram)) {
        if (w.includes(' ')) extra.push(...tokenize(w));
        else extra.push(w);
      }
    }
  }
  return [...base, ...extra];
}

function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    let prev = i - 1;
    row[0] = i;
    for (let j = 1; j <= b.length; j += 1) {
      const tmp = row[j];
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + cost);
      prev = tmp;
    }
  }
  return row[b.length];
}

function tokenMatches(queryToken: string, phraseToken: string): boolean {
  if (queryToken === phraseToken) return true;
  const expanded = expand(queryToken);
  if (expanded.has(phraseToken)) return true;
  for (const alt of expand(phraseToken)) {
    if (expanded.has(alt)) return true;
  }
  if (queryToken.length >= 4 && phraseToken.length >= 4 && levenshtein(queryToken, phraseToken) <= 2) {
    return true;
  }
  return false;
}

function phraseScore(originalTokens: string[], matchTokens: string[], phrase: string): number {
  const phraseTokens = tokenize(phrase);
  if (!phraseTokens.length || !originalTokens.length) return 0;
  let matched = 0;
  for (const pt of phraseTokens) {
    if (matchTokens.some((qt) => tokenMatches(qt, pt))) matched += 1;
  }
  const coverage = matched / phraseTokens.length;
  let queryHits = 0;
  for (const qt of originalTokens) {
    if (phraseTokens.some((pt) => tokenMatches(qt, pt))) queryHits += 1;
  }
  const recall = queryHits / originalTokens.length;
  return coverage * 0.55 + recall * 0.45;
}

function bestScore(intent: HelpIntent, originalTokens: string[], matchTokens: string[], originalJoined: string): number {
  const phrases = [intent.canonicalQuestion, ...intent.userQueries];
  let best = 0;
  for (const phrase of phrases) {
    const phraseTokens = tokenize(phrase);
    if (phraseTokens.length && phraseTokens.join(' ') === originalJoined) {
      return 1;
    }
    const s = phraseScore(originalTokens, matchTokens, phrase);
    if (s > best) best = s;
  }
  return best;
}

const CONFIDENT = 0.42;
const AMBIGUOUS_GAP = 0.08;

function resolveHelpQueryUncached(trimmed: string): ResolverResult {
  if (!trimmed) {
    return { state: 'no-match', intent: null, hits: [], chips: [], categoryHint: null };
  }

  const chips = ambiguityChips(trimmed);
  if (isAmbiguousKey(trimmed) && tokenize(trimmed).length <= 3) {
    return {
      state: 'ambiguous',
      intent: null,
      hits: [],
      chips,
      categoryHint: null,
    };
  }

  const originalTokens = tokenize(trimmed);
  const matchTokens = expandedQueryTokens(trimmed);
  const originalJoined = originalTokens.join(' ');
  const hits: ResolverHit[] = HELP_INTENTS.map((intent) => ({
    intent,
    score: bestScore(intent, originalTokens, matchTokens, originalJoined),
  }))
    .filter((h) => h.score > 0.12)
    .sort((a, b) => b.score - a.score || b.intent.priority - a.intent.priority);

  if (!hits.length) {
    return {
      state: 'no-match',
      intent: null,
      hits: [],
      chips: [],
      categoryHint: HELP_INTENTS[0]?.category ?? 'Bills',
    };
  }

  const top = hits[0];
  const second = hits[1];
  if (chips.length && top.score < 0.72) {
    return { state: 'ambiguous', intent: null, hits: hits.slice(0, 5), chips, categoryHint: top.intent.category };
  }
  if (top.score >= CONFIDENT && (!second || top.score - second.score >= AMBIGUOUS_GAP)) {
    const state = top.intent.type === 6 && (top.intent.diagnosis?.length ?? 0) > 0 ? 'diagnostic' : 'confident';
    return { state, intent: top.intent, hits: hits.slice(0, 5), chips: [], categoryHint: top.intent.category };
  }
  if (hits.length > 1 && top.score - (second?.score ?? 0) < AMBIGUOUS_GAP) {
    if (chips.length) {
      return {
        state: 'ambiguous',
        intent: null,
        hits: hits.slice(0, 5),
        chips,
        categoryHint: top.intent.category,
      };
    }
    // F3-052: the two top hits are genuinely tied (gap < AMBIGUOUS_GAP) and
    // there are no disambiguation chips to show. type-6 intents still offer a
    // real chooser via DiagnosisPicker, so let those through as 'diagnostic' —
    // but a plain intent must not be answered as 'confident' on a coin flip;
    // fall through to 'no-match' (which shows the tied hits, not a picked one).
    if (top.score >= CONFIDENT && top.intent.type === 6 && (top.intent.diagnosis?.length ?? 0) > 0) {
      return { state: 'diagnostic', intent: top.intent, hits: hits.slice(0, 5), chips: [], categoryHint: top.intent.category };
    }
    return {
      state: 'no-match',
      intent: null,
      hits: hits.slice(0, 5),
      chips: [],
      categoryHint: top.intent.category,
    };
  }
  if (top.score >= CONFIDENT) {
    const state = top.intent.type === 6 && (top.intent.diagnosis?.length ?? 0) > 0 ? 'diagnostic' : 'confident';
    return { state, intent: top.intent, hits: hits.slice(0, 5), chips: [], categoryHint: top.intent.category };
  }
  return {
    state: 'no-match',
    intent: null,
    hits: hits.slice(0, 3),
    chips: [],
    categoryHint: top.intent.category,
  };
}

export function resolveHelpQuery(query: string): ResolverResult {
  const trimmed = query.trim();
  const cached = queryCache.get(trimmed);
  if (cached) return cached;
  const result = resolveHelpQueryUncached(trimmed);
  if (queryCache.size >= CACHE_MAX) {
    const first = queryCache.keys().next().value;
    if (first !== undefined) queryCache.delete(first);
  }
  queryCache.set(trimmed, result);
  return result;
}

export const QUESTION_RE = /^(how|why|what|can|kaise|kyu|kyun|kya|kaha|kahaan)\b/i;

export function queryLooksLikeQuestion(query: string): boolean {
  const q = query.trim();
  if (QUESTION_RE.test(q)) return true;
  const result = resolveHelpQuery(q);
  return result.state === 'confident' || result.state === 'ambiguous' || result.state === 'diagnostic';
}

export function helpHitsForSearch(query: string, max = 3): { intent: HelpIntent; score: number }[] {
  const result = resolveHelpQuery(query);
  if (result.state === 'no-match') return [];
  if (result.intent) return [{ intent: result.intent, score: result.hits[0]?.score ?? 1 }];
  return result.hits.slice(0, max);
}

export { getHelpIntent };
