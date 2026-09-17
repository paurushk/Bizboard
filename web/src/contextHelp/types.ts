import type { LocalizedText } from '@/pages/help/types';

export type { LocalizedText };

export interface ContextHelpRelatedPage {
  path: string;
  /** i18n key, e.g. `nav.receipts`. */
  labelKey: string;
}

export interface ContextHelpPage {
  id: string;
  title: LocalizedText;
  summary: LocalizedText;
  howItWorks: LocalizedText[];
  businessImpact: LocalizedText[];
  keyRules: LocalizedText[];
  commonMistakes: LocalizedText[];
  relatedPages: ContextHelpRelatedPage[];
  nextActions: LocalizedText[];
}
