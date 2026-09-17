import type { ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
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
  error?: string | null;
  errorSource?: unknown;
  documentId?: string | number;
  multiGodown?: boolean;
  warning?: string | null;
  infoBanner?: ReactNode;
  saving?: boolean;
  onPrimarySave: () => void;
  onSaveAndNew?: () => void;
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
  error,
  errorSource,
  documentId,
  multiGodown = false,
  warning,
  infoBanner,
  saving = false,
  onPrimarySave,
  onSaveAndNew,
  onDraft,
  onOpenShortcuts,
  onOpenSettings,
  hideSaveAndNew = false,
  hideSettings = false,
  hideShortcuts = false,
  extraActions,
  children,
  helpPage,
}: DocumentEditorShellProps) {
  const { writesBlocked } = useSubscriptionGate();
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
        : primaryDisabledReason || t('billing.completeDisabledReason');
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
          {primarySave.mode === 'complete' ? (
            <FieldHelpTip slot="complete" title={t('help.completeTip')} />
          ) : null}
          <Tooltip
            title={
              primaryDisabled
                ? primarySave.mode === 'save'
                  ? saveTooltip
                  : completeTooltip
                : ''
            }
          >
            <span>
              <Button variant="contained" disabled={primaryDisabled} onClick={onPrimarySave}>
                {t(primarySave.labelKey)}
              </Button>
            </span>
          </Tooltip>
          {!hideSaveAndNew && onSaveAndNew ? (
            <Tooltip
              title={
                writesBlocked || !canComplete
                  ? completeTooltip
                  : ''
              }
            >
            <span>
            <Button
              variant="outlined"
              disabled={writesBlocked || !canComplete || isEdit || saving}
              onClick={onSaveAndNew}
            >
              {t('billing.saveAndNew')}
            </Button>
            </span>
            </Tooltip>
          ) : null}
          {showDraftButton && onDraft ? (
            <Button size="small" disabled={writesBlocked || !canSave || saving} onClick={onDraft}>
              {t('common.draft')}
            </Button>
          ) : null}
          {extraActions}
          {backTo ? (
            <Button size="small" component={RouterLink} to={backTo}>
              {t('common.back')}
            </Button>
          ) : null}
        </Stack>
      </Stack>

      {message ? (
        <Alert severity="success" sx={{ transition: 'opacity 200ms ease' }}>
          {message}
        </Alert>
      ) : null}
      {error ? (
        <HelpErrorAlert message={error} error={errorSource} invoiceId={documentId} />
      ) : null}
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      {isHelpV2Enabled() && primarySave.mode === 'complete' ? (
        <PreventionNote intent="cannot-complete-invoice" slot="invoice-complete" multiGodown={multiGodown} />
      ) : null}
      {infoBanner}

      <Box>{children}</Box>
    </Stack>
  );
}
