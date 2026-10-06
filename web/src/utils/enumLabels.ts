import { t } from '@/i18n';

/** Groups of backend codes that people see in lists, filters and buttons. Labels live in `enums.*` (en and hi). */
export type EnumGroup =
  | 'complaintCategory'
  | 'complaintStatus'
  | 'ticketStatus'
  | 'ticketPriority'
  | 'contractType'
  | 'contractStatus'
  | 'campaignType'
  | 'campaignStatus'
  | 'rewardType'
  | 'insuranceLine'
  | 'opportunityStage'
  | 'leadSource';

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .filter(Boolean)
    .map((part, i) => (i === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(' ');
}

/** Plain-language label for a backend code. An unknown code falls back to "Title case", never the raw ALL_CAPS. */
export function enumLabel(group: EnumGroup, value: string | null | undefined): string {
  const code = String(value ?? '').trim();
  if (!code) return '—';
  const key = `enums.${group}.${code}`;
  const label = t(key);
  return label === key ? titleCase(code) : label;
}
