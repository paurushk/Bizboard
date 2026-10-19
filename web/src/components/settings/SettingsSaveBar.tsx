import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { t } from '@/i18n';
import type { SettingsForm } from '@/hooks/useSettingsForm';

/**
 * SET-11: sticky Save / Discard bar plus the leave guard and the "changed by someone else"
 * dialog, all driven by one `useSettingsForm` result.
 */
export function SettingsSaveBar<TValues extends object, TResult>({
  form,
  disabled = false,
  sticky = true,
}: {
  form: SettingsForm<TValues, TResult>;
  /** False when a page has several forms, so each Save bar sits under its own section. */
  sticky?: boolean;
  /** E.g. subscription writes blocked. */
  disabled?: boolean;
}) {
  const status = form.saving
    ? t('settingsShell.saving')
    : form.dirty
      ? t('settingsShell.unsaved')
      : form.savedAt
        ? t('settingsShell.saved')
        : '';
  return (
    <>
      <UnsavedChangesGuard when={form.dirty && !form.saving} />
      <Paper
        variant="outlined"
        sx={sticky ? { position: 'sticky', bottom: 0, zIndex: 2, p: 1.5, mt: 2 } : { p: 1.5 }}
        role="region"
        aria-label={t('settingsShell.saveBar')}
      >
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
          <Typography variant="body2" color="text.secondary" sx={{ flexGrow: 1 }} aria-live="polite">
            {status}
          </Typography>
          <Button onClick={form.discard} disabled={!form.dirty || form.saving}>
            {t('settingsShell.discard')}
          </Button>
          <Button variant="contained" onClick={() => void form.save()} disabled={disabled || !form.dirty || form.saving}>
            {t('common.save')}
          </Button>
        </Stack>
      </Paper>
      <Dialog open={form.conflict !== null} onClose={form.dismissConflict} aria-labelledby="settings-conflict-title">
        <DialogTitle id="settings-conflict-title">{t('settingsShell.conflictTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('settingsShell.conflictBody')}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={form.dismissConflict}>{t('common.cancel')}</Button>
          <Button onClick={() => void form.resolveConflict('overwrite')}>{t('settingsShell.overwrite')}</Button>
          <Button variant="contained" onClick={() => void form.resolveConflict('reload')}>
            {t('settingsShell.reload')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
