import { useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import KeyboardIcon from '@mui/icons-material/Keyboard';
import SettingsIcon from '@mui/icons-material/Settings';
import { Link as RouterLink } from 'react-router-dom';
import { FieldHelpTip, PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { PreventionNote } from '@/pages/help/PreventionNote';
import { isHelpV2Enabled } from '@/config/features';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import type { PrimarySaveAction } from '@/hooks/useBillingSaveFeedback';

export interface DocumentEditorShellProps {
  title: string;
  primarySave: PrimarySaveAction;
  canSave: boolean;
  canComplete: boolean;
  /** When editing a completed doc, primary "save" may require owner. */
  primaryDisabledExtra?: boolean;
  /** Page-specific reason when Complete / Save & New is disabled. */
  primaryDisabledReason?: string;
  isEdit: boolean;
  showDraftButton?: boolean;
  backTo?: string | null;
  message?: string | null;
  messageAction?: ReactNode;
  error?: string | null;
  errorSource?: unknown;
  onDismissError?: () => void;
  documentId?: string | number;
  multiGodown?: boolean;
  warning?: string | null;
  infoBanner?: ReactNode;
  saving?: boolean;
  onPrimarySave: () => void;
  onSaveAndNew?: () => void;
  /** BUG-UI-015: draft a voucher and open another when Complete is still blocked. */
  onSaveDraftAndNew?: () => void;
  onDraft?: () => void;
  onOpenShortcuts?: () => void;
  onOpenSettings?: () => void;
  hideSaveAndNew?: boolean;
  hideSettings?: boolean;
  hideShortcuts?: boolean;
  extraActions?: ReactNode;
  children: ReactNode;
  /** Catalog id; omit to resolve from the current route. */
  helpPage?: string;
  /** UX-N14: names the party in the generic "why is Complete off" hint. */
  partyRole?: 'customer' | 'supplier';
  /** A2-8: when nothing is chosen yet, move focus to the party or the first item. */
  onFocusMissing?: () => void;
}

function useDismissedError(error?: string | null, source?: unknown) {
  // The dismissal is remembered by message AND by the error object behind it. A new failure with
  // the same words (the same stock shortage on the next Complete click) is a new error object, so
  // it shows again instead of looking like the click did nothing.
  const [dismissed, setDismissed] = useState<{ message: string; source: unknown } | null>(null);
  // Forget the dismissal once the error clears, so the same message can show again on a retry.
  if (!error && dismissed !== null) setDismissed(null);
  const stillDismissed =
    dismissed !== null && dismissed.message === error && (source === undefined || dismissed.source === source);
  const shown = error && !stillDismissed ? error : null;
  return {
    shown,
    dismiss: () => {
      if (error) setDismissed({ message: error, source });
    },
  };
}

/**
 * Shared chrome for billing document editors (P0-311).
 * Pages own form state/mutations; this owns layout, alerts, and primary actions.
 */
export function DocumentEditorShell({
  title,
  primarySave,
  canSave,
  canComplete,
  primaryDisabledExtra = false,
  primaryDisabledReason,
  isEdit,
  showDraftButton = true,
  backTo,
  message,
  messageAction,
  error,
  errorSource,
  onDismissError,
  documentId,
  multiGodown = false,
  warning,
  infoBanner,
  saving = false,
  onPrimarySave,
  onSaveAndNew,
  onSaveDraftAndNew,
  onDraft,
  onOpenShortcuts,
  onOpenSettings,
  hideSaveAndNew = false,
  hideSettings = false,
  hideShortcuts = false,
  extraActions,
  children,
  helpPage,
  partyRole,
  onFocusMissing,
}: DocumentEditorShellProps) {
  const editorError = useDismissedError(error, errorSource);
  const { writesBlocked } = useSubscriptionGate();
  const genericCompleteReason =
    partyRole === 'customer'
      ? t('billing.completeDisabledReasonCustomer')
      : partyRole === 'supplier'
        ? t('billing.completeDisabledReasonSupplier')
        : t('billing.completeDisabledReason');
  const primaryDisabled =
    writesBlocked ||
    saving ||
    (primarySave.mode === 'save'
      ? !canSave || primaryDisabledExtra
      : !canComplete);
  const completeTooltip = writesBlocked
    ? t('billing.writesBlocked')
    : saving
      ? t('billing.completeDisabledSaving')
      : primaryDisabledExtra && primarySave.mode === 'save'
        ? primaryDisabledReason || t('billing.saveDisabledReason')
        : primaryDisabledReason || genericCompleteReason;
  const showFocusMissing =
    Boolean(onFocusMissing) &&
    primarySave.mode === 'complete' &&
    !writesBlocked &&
    !saving &&
    !canComplete &&
    !primaryDisabledReason;
  const saveTooltip = writesBlocked
    ? t('billing.writesBlocked')
    : saving
      ? t('billing.completeDisabledSaving')
      : primaryDisabledReason || t('billing.saveDisabledReason');

  return (
    <Stack
      spacing={2}
      sx={{
        pb: 4,
        '@keyframes billingFadeIn': {
          from: { opacity: 0, transform: 'translateY(6px)' },
          to: { opacity: 1, transform: 'translateY(0)' },
        },
        animation: 'billingFadeIn 280ms ease-out',
      }}
    >
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="center"
        flexWrap="wrap"
        gap={1}
      >
        <PageTitle page={helpPage}>{title}</PageTitle>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          {!hideShortcuts && onOpenShortcuts ? (
            <Tooltip title={t('billing.shortcuts')}>
              <IconButton size="small" aria-label={t('a11y.shortcuts')} onClick={onOpenShortcuts}>
                <KeyboardIcon />
              </IconButton>
            </Tooltip>
          ) : null}
          {!hideSettings && onOpenSettings ? (
            <Button
              startIcon={<SettingsIcon />}
              variant="outlined"
              size="small"
              onClick={onOpenSettings}
            >
              {t('billing.settings')}
            </Button>
          ) : null}
          {backTo ? (
            <Button size="small" component={RouterLink} to={backTo}>
              {t('common.back')}
            </Button>
          ) : null}
        </Stack>
      </Stack>

      {message ? (
        <Alert severity="success" action={messageAction} sx={{ transition: 'opacity 200ms ease' }}>
          {message}
        </Alert>
      ) : null}
      {editorError.shown ? (
        <HelpErrorAlert
          message={editorError.shown}
          error={errorSource}
          invoiceId={documentId}
          onClose={() => {
            editorError.dismiss();
            onDismissError?.();
          }}
        />
      ) : null}
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      {isHelpV2Enabled() && primarySave.mode === 'complete' ? (
        <PreventionNote intent="cannot-complete-invoice" slot="invoice-complete" multiGodown={multiGodown} />
      ) : null}
      {infoBanner}

      <Box>{children}</Box>
      <Box
        sx={{
          position: 'sticky',
          bottom: 0,
          zIndex: 2,
          bgcolor: 'background.paper',
          borderTop: 1,
          borderColor: 'divider',
          pt: 1,
          px: 0.5,
          pb: 'calc(env(safe-area-inset-bottom) + 8px)',
        }}
      >
        {primaryDisabled ? (
          <Typography id="complete-disabled-reason" variant="body2" sx={{ mb: 1 }}>
            {primarySave.mode === 'save' ? saveTooltip : completeTooltip}
          </Typography>
        ) : null}
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          {primarySave.mode === 'complete' ? (
            <FieldHelpTip slot="complete" title={t('help.completeTip')} />
          ) : null}
          <Tooltip title={primaryDisabled ? (primarySave.mode === 'save' ? saveTooltip : completeTooltip) : ''}>
            <span>
              <Button
                variant="contained"
                disabled={primaryDisabled}
                onClick={onPrimarySave}
                aria-describedby={primaryDisabled ? 'complete-disabled-reason' : undefined}
              >
                {t(primarySave.labelKey)}
              </Button>
            </span>
          </Tooltip>
          {showFocusMissing ? (
            <Button variant="outlined" onClick={onFocusMissing}>
              {t('billing.focusMissingField')}
            </Button>
          ) : null}
          {!hideSaveAndNew && (onSaveAndNew || onSaveDraftAndNew) ? (
            <Button
              variant="outlined"
              disabled={writesBlocked || saving || isEdit || !canSave || (canComplete ? !onSaveAndNew : !onSaveDraftAndNew)}
              onClick={canComplete ? onSaveAndNew : onSaveDraftAndNew}
            >
              {canComplete ? t('billing.saveAndNew') : t('billing.saveDraftAndNew')}
            </Button>
          ) : null}
          {showDraftButton && onDraft ? (
            <Button size="small" disabled={writesBlocked || !canSave || saving} onClick={onDraft}>
              {t('common.draft')}
            </Button>
          ) : null}
          {extraActions}
        </Stack>
      </Box>
    </Stack>
  );
}
