import type { ContextHelpPage, ContextHelpRelatedPage, LocalizedText } from './types';

export type Pair = readonly [string, string];

export function loc(en: string, hi: string): LocalizedText {
  return { en, hi };
}

export function locList(pairs: readonly Pair[]): LocalizedText[] {
  return pairs.map(([en, hi]) => loc(en, hi));
}

export function helpPage(
  id: string,
  spec: {
    title: Pair;
    summary: Pair;
    howItWorks: readonly Pair[];
    businessImpact: readonly Pair[];
    keyRules: readonly Pair[];
    commonMistakes: readonly Pair[];
    relatedPages: readonly ContextHelpRelatedPage[];
    nextActions: readonly Pair[];
  },
): ContextHelpPage {
  return {
    id,
    title: loc(spec.title[0], spec.title[1]),
    summary: loc(spec.summary[0], spec.summary[1]),
    howItWorks: locList(spec.howItWorks),
    businessImpact: locList(spec.businessImpact),
    keyRules: locList(spec.keyRules),
    commonMistakes: locList(spec.commonMistakes),
    relatedPages: [...spec.relatedPages],
    nextActions: locList(spec.nextActions),
  };
}

/** Unique screen copy that reuses rules/impact from a sibling page. */
export function helpVariant(
  base: ContextHelpPage,
  id: string,
  patch: {
    title: Pair;
    summary: Pair;
    howItWorks: readonly Pair[];
    nextActions: readonly Pair[];
    relatedPages?: readonly ContextHelpRelatedPage[];
    businessImpact?: readonly Pair[];
    keyRules?: readonly Pair[];
    commonMistakes?: readonly Pair[];
  },
): ContextHelpPage {
  return helpPage(id, {
    title: patch.title,
    summary: patch.summary,
    howItWorks: patch.howItWorks,
    businessImpact: patch.businessImpact ?? base.businessImpact.map((t) => [t.en, t.hi ?? t.en] as Pair),
    keyRules: patch.keyRules ?? base.keyRules.map((t) => [t.en, t.hi ?? t.en] as Pair),
    commonMistakes: patch.commonMistakes ?? base.commonMistakes.map((t) => [t.en, t.hi ?? t.en] as Pair),
    relatedPages: patch.relatedPages ?? base.relatedPages,
    nextActions: patch.nextActions,
  });
}

export function mustPage(pages: ContextHelpPage[], id: string): ContextHelpPage {
  const page = pages.find((row) => row.id === id);
  if (!page) throw new Error(`context help base missing: ${id}`);
  return page;
}
