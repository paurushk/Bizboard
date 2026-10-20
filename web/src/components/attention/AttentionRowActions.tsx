import Button from '@mui/material/Button';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import type { AttentionRow } from '@/types/domain';
import { safeAppPath } from '@/utils/safeUrl';
import { attentionActionLabel } from './rowText';

const touch = { minHeight: { xs: 44, sm: 30 } };

/** The buttons for one problem. The same set is drawn in the table row and in the phone card. */
export function AttentionRowActions({
  row,
  setAside,
  assignmentOn,
  describedBy,
  reopenBusy,
  dismissBusy,
  onFix,
  onReopen,
  onAssign,
  onSnooze,
  onDismiss,
}: {
  row: AttentionRow;
  /** True on the Snoozed and Dismissed lists, where the action is Reopen. */
  setAside: boolean;
  assignmentOn: boolean;
  /** Id of the element holding the row's title, so each button is described by its row. */
  describedBy: string;
  reopenBusy: boolean;
  dismissBusy: boolean;
  onFix: () => void;
  onReopen: () => void;
  onAssign: () => void;
  onSnooze: () => void;
  onDismiss: () => void;
}) {
  return (
    <>
      <Button
        component={RouterLink}
        to={safeAppPath(row.actionHref, '/attention')}
        size="small"
        variant={setAside ? 'text' : 'contained'}
        aria-describedby={describedBy}
        sx={touch}
        onClick={onFix}
      >
        {attentionActionLabel(row)}
      </Button>
      {setAside ? (
        <Button size="small" aria-describedby={describedBy} sx={touch} disabled={reopenBusy} onClick={onReopen}>
          {t('attention.reopen')}
        </Button>
      ) : (
        <>
          {assignmentOn && row.assignable !== false ? (
            <Button size="small" aria-describedby={describedBy} sx={touch} onClick={onAssign}>
              {t('osPlan.assign')}
            </Button>
          ) : null}
          {row.snoozable !== false ? (
            <Button size="small" aria-describedby={describedBy} sx={touch} onClick={onSnooze}>
              {t('attention.snoozeButton')}
            </Button>
          ) : null}
          {row.dismissible !== false ? (
            <Button size="small" aria-describedby={describedBy} sx={touch} disabled={dismissBusy} onClick={onDismiss}>
              {t('attention.dismiss')}
            </Button>
          ) : null}
        </>
      )}
    </>
  );
}
