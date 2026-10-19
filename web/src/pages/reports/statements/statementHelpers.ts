import { toNumber } from '@/utils/money';

export interface ScheduleLine {
  key: string;
  label: string;
  amount: string | number;
  accounts?: Array<{ code: string; name: string; amount: string | number }>;
}

export interface ScheduleSection {
  key: string;
  label: string;
  amount: string | number;
  lines: ScheduleLine[];
}

export interface ScheduleIii {
  sections: ScheduleSection[];
}

const ASSET_SECTIONS = new Set(['non_current_assets', 'current_assets']);

/** Split the Schedule III balance sheet into the asset side and the equity-and-liabilities side. */
export function splitBalanceSheet(schedule: ScheduleIii | undefined) {
  const sections = schedule?.sections ?? [];
  const assets = sections.filter((s) => ASSET_SECTIONS.has(s.key));
  const equityAndLiabilities = sections.filter((s) => !ASSET_SECTIONS.has(s.key));
  const sum = (list: ScheduleSection[]) => list.reduce((acc, s) => acc + toNumber(s.amount), 0);
  const totalAssets = sum(assets);
  const totalEquityLiabilities = sum(equityAndLiabilities);
  return {
    assets,
    equityAndLiabilities,
    totalAssets,
    totalEquityLiabilities,
    // Equity already contains the year's profit (surplus line), so the two sides are compared as they are.
    difference: totalAssets - totalEquityLiabilities,
  };
}

/** Lines worth showing: a line with no amount and no accounts is a Schedule III heading with nothing in it. */
export function visibleLines(section: ScheduleSection): ScheduleLine[] {
  return section.lines.filter((l) => toNumber(l.amount) !== 0 || (l.accounts?.length ?? 0) > 0);
}
