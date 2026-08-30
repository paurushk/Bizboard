import { useEffect, useRef } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import { Link as RouterLink } from 'react-router-dom';
import Link from '@mui/material/Link';
import { t } from '@/i18n';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { isHelpV2Enabled } from '@/config/features';
import { HELP_EVENTS, trackHelpEvent } from './analytics';
import { getHelpIntent } from './intents';
import { HelpRichText } from './HelpRichText';

export function PreventionNote({
  intent: intentId,
  slot,
  multiGodown = false,
}: {
  intent: string;
  slot: string;
  multiGodown?: boolean;
}) {
  useFeatureFlagEpoch();
  const enabled = isHelpV2Enabled();
  const rootRef = useRef<HTMLDivElement>(null);
  const seenRef = useRef(false);
  const intent = getHelpIntent(intentId);
  const notes = (intent?.prevention ?? []).filter((p) => {
    if (p.slot !== slot) return false;
    if (p.appliesWhen === 'multi-godown') return multiGodown;
    return true;
  });

  useEffect(() => {
    if (!enabled || !notes.length || seenRef.current) return undefined;
    const el = rootRef.current;
    const fire = () => {
      if (seenRef.current) return;
      seenRef.current = true;
      trackHelpEvent(HELP_EVENTS.PREVENTION_VIEW, { slot, intent: intentId });
    };
    if (!el || typeof IntersectionObserver === 'undefined') {
      fire();
      return undefined;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          fire();
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [enabled, intentId, slot, notes.length]);

  if (!enabled || !notes.length) return null;
  return (
    <Box ref={rootRef}>
      <Alert severity="info" sx={{ '& .MuiAlert-message': { width: '100%' } }}>
        {notes.map((note) => (
          <HelpRichText key={note.text} text={note.text} variant="body2" />
        ))}
        <Link component={RouterLink} to={`/help?intent=${intentId}`} variant="caption">
          {t('help.readMore')}
        </Link>
      </Alert>
    </Box>
  );
}
