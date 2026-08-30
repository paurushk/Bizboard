export const HELP_EVENTS = {
  OPEN: 'help_open',
  SEARCH: 'help_search',
  RESOLVED: 'faq_resolved',
  UNDERSTOOD: 'faq_understood_pending',
  UNRESOLVED: 'faq_unresolved',
  DIAGNOSIS_BRANCH: 'diagnosis_branch',
  PREVENTION_VIEW: 'prevention_view',
  NEXTSTEP: 'faq_nextstep_click',
} as const;

export type HelpEventName = (typeof HELP_EVENTS)[keyof typeof HELP_EVENTS];
