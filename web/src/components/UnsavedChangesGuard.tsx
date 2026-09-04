import { useEffect } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { useBlocker } from 'react-router-dom';
import { t } from '@/i18n';

/** Warn before in-app navigation, a reload, or a tab close discards unsaved work. */
export function UnsavedChangesGuard({ when }: { when: boolean }) {
  const blocker = useBlocker(when);

  // F3-015: useBlocker only covers in-app (react-router) navigation — it has
  // no opinion on a reload or tab close. Every caller of this guard wants
  // both, so cover the hard-navigation case here once instead of asking each
  // page to also wire its own beforeunload listener.
  useEffect(() => {
    if (!when) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [when]);

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
