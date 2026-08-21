import type { ReactNode } from 'react';
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
import { t } from '@/i18n';
import type { PrimarySaveAction } from '@/hooks/useBillingSaveFeedback';

export interface DocumentEditorShellProps {
  title: string;
  primarySave: PrimarySaveAction;
  canSave: boolean;
  canComplete: boolean;
  /** When editing a completed doc, primary "save" may require owner. */
  primaryDisabledExtra?: boolean;
  isEdit: boolean;
  showDraftButton?: boolean;
  backTo?: string | null;
  message?: string | null;
  error?: string | null;
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
  isEdit,
  showDraftButton = true,
  backTo,
  message,
  error,
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
}: DocumentEditorShellProps) {
  const primaryDisabled =
    saving ||
    (primarySave.mode === 'save'
      ? !canSave || primaryDisabledExtra
      : !canComplete);

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
        <Typography variant="h4">{title}</Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          {!hideShortcuts && onOpenShortcuts ? (
            <Tooltip title={t('billing.shortcuts')}>
              <IconButton size="small" aria-label="shortcuts" onClick={onOpenShortcuts}>
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
          <Tooltip title={primaryDisabled ? (primarySave.mode === 'save' ? 'Select a party and at least one line item to save' : 'Select a customer/supplier and at least one item with valid quantity to complete') : ''}>
            <span>
              <Button variant="contained" disabled={primaryDisabled} onClick={onPrimarySave}>
                {t(primarySave.labelKey)}
              </Button>
            </span>
          </Tooltip>
          {!hideSaveAndNew && onSaveAndNew ? (
            <Button
              variant="outlined"
              disabled={!canComplete || isEdit || saving}
              onClick={onSaveAndNew}
            >
              {t('billing.saveAndNew')}
            </Button>
          ) : null}
          {showDraftButton && onDraft ? (
            <Button size="small" disabled={!canSave || saving} onClick={onDraft}>
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
      {error ? <Alert severity="error">{error}</Alert> : null}
      {warning ? <Alert severity="warning">{warning}</Alert> : null}
      {infoBanner}

      <Box>{children}</Box>
    </Stack>
  );
}
