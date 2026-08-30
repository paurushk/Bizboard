import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import CloseIcon from '@mui/icons-material/Close';
import { t } from '@/i18n';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';
import { HELP_EVENTS, trackHelpEvent } from './analytics';
import { getHelpIntent } from './intents';
import { IntentBody } from './IntentBody';
import { HelpFeedbackForm } from './HelpFeedbackForm';
import type { HelpContext } from './types';

export function HelpHint({
  intent: intentId,
  slot,
  children,
}: {
  intent: string;
  slot: string;
  children?: ReactNode;
}) {
  useFeatureFlagEpoch();
  const [open, setOpen] = useState(false);
  const intent = getHelpIntent(intentId);
  if (!isHelpV2Enabled() || !intent) return <>{children}</>;
  return (
    <>
      <Box
        data-testid="help-hint-wrap"
        sx={{
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'flex-start',
          gap: 0.25,
          minWidth: 0,
          width: '100%',
          maxWidth: '100%',
          '& > :first-of-type': { flex: '1 1 auto', minWidth: 0, maxWidth: '100%' },
        }}
      >
        {children}
        <IconButton
          size="small"
          aria-label={t('help.hintAria')}
          onClick={() => {
            setOpen(true);
            trackHelpEvent(HELP_EVENTS.OPEN, { source: 'field', intentId, slot });
          }}
        >
          <HelpOutlineIcon fontSize="inherit" />
        </IconButton>
      </Box>
      <HelpIntentDrawer
        open={open}
        onClose={() => setOpen(false)}
        intentId={intentId}
        context={{ from: slot, screen: slot }}
      />
    </>
  );
}

export function HelpIntentDrawer({
  open,
  onClose,
  intentId,
  context,
}: {
  open: boolean;
  onClose: () => void;
  intentId: string;
  context?: HelpContext;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const intent = getHelpIntent(intentId);

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      ModalProps={{ keepMounted: false }}
      PaperProps={{
        sx: { width: { xs: '100%', sm: 420 }, p: 2 },
        'aria-labelledby': titleId,
      }}
    >
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography id={titleId} variant="h6">
            {intent?.canonicalQuestion ?? t('help.title')}
          </Typography>
          <IconButton ref={closeRef} aria-label={t('common.close')} onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </Stack>
        {intent ? <IntentBody intent={intent} context={context} /> : <Typography>{t('help.noResults')}</Typography>}
        {intent ? (
          <HelpFeedbackForm intentId={intent.intentId} surface={`drawer:${context?.from ?? 'hint'}`} />
        ) : null}
      </Stack>
    </Drawer>
  );
}
