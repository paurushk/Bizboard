import { useContext, useEffect } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { UNSAFE_DataRouterContext, useBlocker } from 'react-router-dom';
import { t } from '@/i18n';
import { trackShopFloor } from '@/lib/telemetry';

type GuardCopy = {
  when: boolean;
  /** Open the same confirm for a dirty dialog dismiss. Route blocking stays on `when`. */
  prompt?: boolean;
  title?: string;
  body?: string;
  leaveLabel?: string;
  onStay?: () => void;
  onLeave?: () => void;
};

function DataRouterBlocker({ when, title, body, leaveLabel, onLeave }: Required<Pick<GuardCopy, 'when' | 'title' | 'body' | 'leaveLabel'>> & Pick<GuardCopy, 'onLeave'>) {
  const blocker = useBlocker(when);

  return (
    <Dialog
      open={blocker.state === 'blocked'}
      onClose={() => blocker.reset?.()}
      aria-labelledby="unsaved-changes-title"
    >
      <DialogTitle id="unsaved-changes-title">{title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2">{body}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => blocker.reset?.()}>{t('common.stay')}</Button>
        <Button
          color="warning"
          variant="contained"
          onClick={() => {
            trackShopFloor('form_abandoned', { feature: 'form' });
            onLeave?.();
            blocker.proceed?.();
          }}
        >
          {leaveLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** Warn before in-app navigation, a reload, or a tab close discards unsaved work. */
export function UnsavedChangesGuard({ when, prompt = false, title, body, leaveLabel, onStay, onLeave }: GuardCopy) {
  const dataRouterCtx = useContext(UNSAFE_DataRouterContext);
  const resolvedTitle = title ?? t('billing.unsavedTitle');
  const resolvedBody = body ?? t('billing.unsavedBody');
  const resolvedLeave = leaveLabel ?? t('common.leave');

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

  const manual = (
    <Dialog open={prompt} onClose={() => onStay?.()} aria-labelledby="unsaved-changes-discard-title">
      <DialogTitle id="unsaved-changes-discard-title">{resolvedTitle}</DialogTitle>
      <DialogContent>
        <Typography variant="body2">{resolvedBody}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => onStay?.()}>{t('common.stay')}</Button>
        <Button color="warning" variant="contained" onClick={() => onLeave?.()}>
          {resolvedLeave}
        </Button>
      </DialogActions>
    </Dialog>
  );

  if (!dataRouterCtx) {
    return prompt ? manual : null;
  }

  return (
    <>
      <DataRouterBlocker
        when={when}
        title={resolvedTitle}
        body={resolvedBody}
        leaveLabel={resolvedLeave}
        onLeave={onLeave}
      />
      {manual}
    </>
  );
}
