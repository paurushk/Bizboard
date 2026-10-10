import { useContext, useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Typography from '@mui/material/Typography';
import { UNSAFE_DataRouterContext, useBlocker, useInRouterContext, useLocation, useNavigate } from 'react-router-dom';
import { t } from '@/i18n';
import { trackShopFloor } from '@/lib/telemetry';

type GuardCopy = {
  when: boolean;
  /** Open the same confirm for a dirty dialog dismiss. Route blocking stays on `when`. */
  prompt?: boolean;
  title?: string;
  body?: string;
  leaveLabel?: string;
  /** Also ask before an in-app link is followed. Only for forms whose `when` is exact: several
   * editors treat a freshly opened saved document as unsaved, and would prompt on every click. */
  interceptLinks?: boolean;
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

/**
 * The app runs on a plain BrowserRouter, which has no blocker. When a form opts in with
 * `interceptLinks` and has unsaved changes, this catches a click on an in-app link (sidebar, breadcrumbs, any anchor to this origin),
 * asks first, and navigates only if the user chooses to leave. Modified clicks, new-tab links,
 * downloads and other origins are left alone. The browser Back button cannot be intercepted
 * here; reload and tab close are covered by the beforeunload handler.
 */
function LinkLeaveGuard({ title, body, leaveLabel }: { title: string; body: string; leaveLabel: string }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [pending, setPending] = useState<string | null>(null);
  const current = location.pathname + location.search + location.hash;

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = (event.target as Element | null)?.closest?.('a[href]') as HTMLAnchorElement | null;
      if (!anchor || anchor.hasAttribute('download')) return;
      if (anchor.target && anchor.target !== '_self') return;
      let url: URL;
      try {
        url = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;
      const next = url.pathname + url.search + url.hash;
      if (next === current) return;
      event.preventDefault();
      event.stopPropagation();
      setPending(next);
    };
    // Capture phase, so this runs before the router's own link handler.
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [current]);

  return (
    <Dialog open={pending != null} onClose={() => setPending(null)} aria-labelledby="unsaved-link-title">
      <DialogTitle id="unsaved-link-title">{title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2">{body}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setPending(null)}>{t('common.stay')}</Button>
        <Button
          color="warning"
          variant="contained"
          onClick={() => {
            const next = pending;
            setPending(null);
            trackShopFloor('form_abandoned', { feature: 'form' });
            if (next) void navigate(next);
          }}
        >
          {leaveLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

/** Warn before in-app navigation, a reload, or a tab close discards unsaved work. */
export function UnsavedChangesGuard({ when, prompt = false, title, body, leaveLabel, interceptLinks = false, onStay, onLeave }: GuardCopy) {
  const dataRouterCtx = useContext(UNSAFE_DataRouterContext);
  const inRouter = useInRouterContext();
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
    return (
      <>
        {when && interceptLinks && inRouter ? <LinkLeaveGuard title={resolvedTitle} body={resolvedBody} leaveLabel={resolvedLeave} /> : null}
        {prompt ? manual : null}
      </>
    );
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
