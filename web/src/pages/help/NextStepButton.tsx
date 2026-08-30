import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import { HELP_EVENTS, trackHelpEvent } from './analytics';
import { HelpRichText } from './HelpRichText';
import { interpolateDestination, userHasHelpPermission, useHelpUser } from './helpPermissions';
import type { HelpContext, HelpNextStep } from './types';

export function NextStepButton({
  nextStep,
  context,
  intentId,
}: {
  nextStep: HelpNextStep;
  context?: HelpContext;
  intentId?: string;
}) {
  const user = useHelpUser();
  const allowed = userHasHelpPermission(user, nextStep.permission);
  const params = {
    id: context?.invoiceId,
    invoiceId: context?.invoiceId,
  };
  const dest = interpolateDestination(nextStep.destination, params);
  const cancelDest = nextStep.cancelDestination
    ? interpolateDestination(nextStep.cancelDestination, params)
    : '';
  const canCancel = Boolean(cancelDest) && userHasHelpPermission(user, 'can_cancel_documents');
  if (!allowed) {
    return (
      <>
        <HelpRichText text={nextStep.fallback} />
        {nextStep.escalation ? <HelpRichText text={nextStep.escalation} /> : null}
      </>
    );
  }
  if (!dest && !canCancel) {
    return <HelpRichText text={nextStep.fallback} />;
  }
  const track = (destination: string) => {
    trackHelpEvent(HELP_EVENTS.NEXTSTEP, { intentId, destination, label: nextStep.label });
  };
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {dest ? (
        <Button
          component={RouterLink}
          to={dest}
          variant="contained"
          size="small"
          onClick={() => track(dest)}
        >
          {nextStep.label}
        </Button>
      ) : null}
      {canCancel ? (
        <Button
          component={RouterLink}
          to={cancelDest}
          variant={context?.from === 'cancel' ? 'contained' : 'outlined'}
          color={context?.from === 'cancel' ? 'error' : 'primary'}
          size="small"
          onClick={() => track(cancelDest)}
        >
          {t('help.cancelThisBill')}
        </Button>
      ) : null}
    </Stack>
  );
}

export function NextStepFallbackNote() {
  return (
    <Typography variant="caption" color="text.secondary">
      {t('help.missingContext')}
    </Typography>
  );
}
