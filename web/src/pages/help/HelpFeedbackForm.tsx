import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { useAuth } from '@/auth/AuthContext';
import { isOwner } from '@/utils/permissions';
import { postHelpFeedback } from '@/api/help';
import { HELP_EVENTS, trackHelpEvent } from './analytics';

export function HelpFeedbackForm({
  intentId,
  query,
  surface,
  captureOnly = false,
}: {
  intentId?: string;
  query?: string;
  surface?: string;
  captureOnly?: boolean;
}) {
  const { user } = useAuth();
  const owner = isOwner(user?.role ?? 'VIEWER');
  const idPart = intentId || (query ? `q:${query.slice(0, 80)}` : 'none');
  const persistKey = `help:fb:${idPart}:${surface ?? 'page'}`;
  const [choice, setChoice] = useState<'resolved' | 'understood' | 'stuck' | null>(null);
  const [note, setNote] = useState('');
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(persistKey);
      if (saved === HELP_EVENTS.RESOLVED) setChoice('resolved');
      else if (saved === HELP_EVENTS.UNDERSTOOD) setChoice('understood');
      else if (saved === HELP_EVENTS.UNRESOLVED) setChoice('stuck');
    } catch {
      // ignore
    }
  }, [persistKey]);

  const persist = (name: string) => {
    try {
      const already = sessionStorage.getItem(persistKey);
      if (already === name) return;
      sessionStorage.setItem(persistKey, name);
    } catch {
      // ignore
    }
    trackHelpEvent(name, { intentId, query });
  };

  const onStuck = async () => {
    setChoice('stuck');
    persist(HELP_EVENTS.UNRESOLVED);
  };

  const submitNote = async () => {
    setSending(true);
    setError(false);
    try {
      await postHelpFeedback({
        intentId,
        query,
        note,
        screen: typeof window !== 'undefined' ? window.location.pathname : '',
      });
      if (captureOnly) persist(HELP_EVENTS.UNRESOLVED);
      setSent(true);
    } catch {
      setError(true);
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return <Alert severity="success">{t('help.feedbackThanks')}</Alert>;
  }

  const noteFields = (
    <Stack spacing={1}>
      {!owner ? <Typography variant="body2">{t('help.askOwner')}</Typography> : null}
      {error ? <Alert severity="error">{t('help.feedbackFailed')}</Alert> : null}
      <TextField
        label={t('help.feedbackNote')}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        multiline
        minRows={2}
        size="small"
      />
      <Button size="small" variant="contained" disabled={sending} onClick={() => void submitNote()}>
        {t('help.sendFeedback')}
      </Button>
    </Stack>
  );

  if (captureOnly) {
    return (
      <Stack spacing={1} sx={{ pt: 1 }}>
        <Typography variant="subtitle2">{t('help.stillStuck')}</Typography>
        {noteFields}
      </Stack>
    );
  }

  return (
    <Stack spacing={1} sx={{ pt: 1 }}>
      <Typography variant="subtitle2">{t('help.wasThisHelpful')}</Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant={choice === 'resolved' ? 'contained' : 'outlined'}
          onClick={() => {
            setChoice('resolved');
            persist(HELP_EVENTS.RESOLVED);
          }}
        >
          {t('help.solvedIt')}
        </Button>
        <Button
          size="small"
          variant={choice === 'understood' ? 'contained' : 'outlined'}
          onClick={() => {
            setChoice('understood');
            persist(HELP_EVENTS.UNDERSTOOD);
          }}
        >
          {t('help.understoodNotDone')}
        </Button>
        <Button
          size="small"
          variant={choice === 'stuck' ? 'contained' : 'outlined'}
          onClick={() => void onStuck()}
        >
          {t('help.stillStuck')}
        </Button>
      </Stack>
      {choice === 'stuck' ? noteFields : null}
    </Stack>
  );
}
