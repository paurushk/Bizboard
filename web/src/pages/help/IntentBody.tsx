import Stack from '@mui/material/Stack';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { t, getLocale } from '@/i18n';
import { HelpRichText } from './HelpRichText';
import { NextStepButton } from './NextStepButton';
import type { HelpContext, HelpIntent, HelpNextStep, LocalizedText } from './types';

function pick(text: LocalizedText): { value: string; fallbackHi: boolean } {
  const locale = getLocale();
  if (locale === 'hi' && text.hi) return { value: text.hi, fallbackHi: false };
  if (locale === 'hi' && !text.hi) return { value: text.en, fallbackHi: true };
  return { value: text.en, fallbackHi: false };
}

export function IntentBody({
  intent,
  context,
  answer,
  action,
  resolution,
  nextStep,
  hideNextStep,
}: {
  intent?: HelpIntent;
  context?: HelpContext;
  answer?: string;
  action?: string;
  resolution?: string;
  nextStep?: HelpNextStep;
  hideNextStep?: boolean;
}) {
  const a = answer ?? (intent ? pick(intent.answer).value : '');
  const act = action ?? (intent ? pick(intent.action).value : '');
  const res = resolution ?? (intent ? pick(intent.resolution).value : '');
  const hiMissing = intent ? pick(intent.answer).fallbackHi : false;
  const steps = intent?.resolutionSteps;
  const cta = nextStep ?? intent?.nextStep;

  return (
    <Stack spacing={1.5}>
      {hiMissing ? (
        <Typography variant="caption" color="text.secondary">
          {t('help.hindiSoon')}
        </Typography>
      ) : null}
      <div>
        <Typography variant="overline" color="text.secondary">
          {t('help.answer')}
        </Typography>
        <HelpRichText text={a} />
      </div>
      <div>
        <Typography variant="overline" color="text.secondary">
          {t('help.action')}
        </Typography>
        <HelpRichText text={act} />
      </div>
      <div>
        <Typography variant="overline" color="text.secondary">
          {t('help.resolution')}
        </Typography>
        <HelpRichText text={res} />
        {steps?.length ? (
          <Stack component="ul" sx={{ m: 0, pl: 2 }}>
            {steps.map((step) => (
              <Box key={step} component="li" sx={{ display: 'list-item' }}>
                <HelpRichText text={step} />
              </Box>
            ))}
          </Stack>
        ) : null}
      </div>
      {!hideNextStep && cta ? (
        <NextStepButton nextStep={cta} context={context} intentId={intent?.intentId} />
      ) : null}
    </Stack>
  );
}
