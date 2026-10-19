import { previewSettingsChange, type SettingsPreviewLine } from '@/api/resources';
import { t } from '@/i18n';
import { confirmAction } from '@/utils/confirmBridge';

function sentence(line: SettingsPreviewLine): string {
  const params = Object.fromEntries(
    Object.entries(line.params).map(([k, v]) => [k, k === 'on' ? t(v ? 'settingsHistory.on' : 'settingsHistory.off') : String(v)]),
  );
  const key = line.key === 'cash_days_over_limit' ? `cash_days_over_limit_${line.params.blocked ? 'block' : 'warn'}` : line.key;
  return t(`settingsPreview.${key}`, params);
}

/**
 * SET-22: show the owner what a high-impact change would touch, then ask. If the preview cannot be
 * fetched the owner is still asked, and told the preview was not available, so a failed lookup
 * never silently saves and never blocks a change they have decided to make.
 */
export async function confirmWithPreview(
  area: string,
  proposed: Record<string, unknown>,
  title: string,
): Promise<boolean> {
  let body: string;
  try {
    const lines = await previewSettingsChange(area, proposed);
    body = lines.length ? lines.map((l) => `• ${sentence(l)}`).join('\n') : t('settingsPreview.nothingElse');
  } catch {
    body = t('settingsPreview.unavailable');
  }
  return confirmAction(`${title}\n\n${body}`);
}
