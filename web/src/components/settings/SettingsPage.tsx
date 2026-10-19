import type { ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import { PageShell } from '@/pages/phase/phaseShared';

/**
 * SET-10: the one frame every Settings screen sits in: title, a one-line purpose, an optional state
 * banner, the sections, and a footer slot for the save bar. Where a setting is used is shown by the
 * shared frame above it (`SettingsContinuity`, from the impact registry).
 */
export type SettingsBanner = { severity: 'info' | 'warning' | 'error' | 'success'; text: string };

export function SettingsPage({
  title,
  purpose,
  banner,
  actions,
  helpPage,
  footer,
  children,
}: {
  title: string;
  /** One sentence: what this screen is for. */
  purpose: string;
  /** Page-level state, e.g. "Invoice check is off". */
  banner?: SettingsBanner | SettingsBanner[] | null;
  actions?: ReactNode;
  helpPage?: string;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <PageShell title={title} subtitle={purpose} actions={actions} helpPage={helpPage}>
      {(Array.isArray(banner) ? banner : banner ? [banner] : []).map((b) => (
        <Alert key={b.text} severity={b.severity}>
          {b.text}
        </Alert>
      ))}
      {children}
      {footer}
    </PageShell>
  );
}
