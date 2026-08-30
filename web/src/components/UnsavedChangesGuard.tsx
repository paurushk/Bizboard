import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { useBlocker } from 'react-router-dom';
import { t } from '@/i18n';

/** Warn before in-app navigation discards an unsaved money document. */
export function UnsavedChangesGuard({ when }: { when: boolean }) {
  const blocker = useBlocker(when);

  return (
    <Dialog
      open={blocker.state === 'blocked'}
      onClose={() => blocker.reset?.()}
      aria-labelledby="unsaved-changes-title"
    >
      <DialogTitle id="unsaved-changes-title">{t('billing.unsavedTitle')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2">{t('billing.unsavedBody')}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => blocker.reset?.()}>{t('common.stay')}</Button>
        <Button color="warning" variant="contained" onClick={() => blocker.proceed?.()}>
          {t('common.leave')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
