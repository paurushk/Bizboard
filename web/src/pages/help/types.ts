export type HelpIntentType = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;

export type HelpPermission =
  | 'owner'
  | 'can_create_sales'
  | 'can_create_purchases'
  | 'can_manage_inventory'
  | 'can_import'
  | 'can_post_journals'
  | 'can_cancel_documents'
  | 'can_view_financial_reports';

export type HelpResolverState = 'confident' | 'ambiguous' | 'diagnostic' | 'no-match';

export type HelpOpenSource = 'nav' | 'field' | 'error' | 'empty' | 'search' | 'assistant';

export interface LocalizedText {
  en: string;
  hi?: string;
}

export interface HelpNextStep {
  label: string;
  destination: string;
  permission: HelpPermission;
  fallback: string;
  /** Shown with the fallback when the user lacks permission (HR-4.2). */
  escalation?: string;
  /** Used when Help opened with `from=cancel` (HR-4.3). */
  cancelDestination?: string;
}

export interface HelpDiagnosisLeaf {
  id: string;
  symptom: string;
  intentId?: string;
  answer?: string;
  action?: string;
  resolution?: string;
  nextStep?: HelpNextStep;
  children?: HelpDiagnosisLeaf[];
}

export interface HelpPrevention {
  slot: string;
  text: string;
  appliesWhen?: 'always' | 'multi-godown';
}

export interface HelpIntent {
  intentId: string;
  type: HelpIntentType;
  canonicalQuestion: string;
  userQueries: string[];
  answer: LocalizedText;
  action: LocalizedText;
  resolution: LocalizedText;
  resolutionSteps?: string[];
  errorCodes: string[];
  appliesWhen?: string;
  priority: number;
  category: string;
  diagnosis?: HelpDiagnosisLeaf[];
  nextStep?: HelpNextStep;
  prevention?: HelpPrevention[];
  relatedIntents?: string[];
  /** i18n keys whose English labels appear in this intent (HR-8.2). */
  citedKeys?: string[];
  lastReviewed: string;
}

export interface HelpContext {
  invoiceId?: string | number;
  from?: string;
  screen?: string;
  leaf?: string;
}

export interface ResolverHit {
  intent: HelpIntent;
  score: number;
}

export interface ResolverResult {
  state: HelpResolverState;
  intent: HelpIntent | null;
  hits: ResolverHit[];
  chips: { id: string; label: string; intentId: string }[];
  categoryHint: string | null;
}
