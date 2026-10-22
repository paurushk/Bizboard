import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardActions from '@mui/material/CardActions';
import CardContent from '@mui/material/CardContent';
import Container from '@mui/material/Container';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import {
  applyQueued,
  flushTabletQueue,
  isOffline,
  rememberTabletOperator,
  tabletCards,
  tabletErrorMessage,
  tabletLogin,
  tabletQueue,
  tabletTap,
  type JobCard,
  type TabletVerb,
} from '@/api/mfg';
import { t } from '@/i18n';
import { NumField, Pill, qty } from './mfgShared';

const TOKEN_KEY = 'bb.floor.token';
const NAME_KEY = 'bb.floor.name';

/**
 * The shop-floor tablet: no account, an operator code and PIN. Open it as /floor?company=<id>.
 * Big buttons, one card at a time, and it signs out by itself when the token ends.
 */
export function FloorTabletPage() {
  const [params] = useSearchParams();
  const company = Number(params.get('company') ?? '');
  const [code, setCode] = useState('');
  const [pin, setPin] = useState('');
  const [, bump] = useState(0);
  const name = sessionStorage.getItem(NAME_KEY) ?? '';
  const signedIn = !!sessionStorage.getItem(TOKEN_KEY);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [good, setGood] = useState<Record<number, string>>({});
  const [bad, setBad] = useState<Record<number, string>>({});
  // Taps kept on this tablet while there was no signal; they are sent, in order, as soon as there is.
  const [waiting, setWaiting] = useState(() => tabletQueue().length);
  const [notice, setNotice] = useState('');

  const signOut = () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(NAME_KEY);
    setPin('');
    bump((n) => n + 1);
  };

  // Polls every 20 seconds; an ended token signs the tablet out by itself.
  const cardsQuery = useQuery({
    queryKey: ['floor-cards', signedIn],
    enabled: signedIn,
    refetchInterval: 20_000,
    retry: false,
    queryFn: async (): Promise<JobCard[]> => {
      try {
        // Every poll first sends what was kept while there was no signal, so the order of taps is never lost.
        if (tabletQueue().length) {
          const out = await flushTabletQueue();
          setWaiting(out.left);
          if (out.refused.length) setError(out.refused.join(' '));
        }
        return await tabletCards();
      } catch (err) {
        if (/Sign in|401|403/.test(tabletErrorMessage(err))) {
          sessionStorage.removeItem(TOKEN_KEY);
          sessionStorage.removeItem(NAME_KEY);
        }
        throw err;
      }
    },
  });
  const offline = cardsQuery.isError && isOffline(cardsQuery.error);
  const cards = applyQueued(cardsQuery.data ?? [], tabletQueue());
  const load = async () => {
    await cardsQuery.refetch();
  };

  const sendWaiting = async () => {
    const out = await flushTabletQueue();
    setWaiting(out.left);
    if (out.refused.length) setError(out.refused.join(' '));
    if (out.sent) await load();
  };
  // Back online, or a poll got through: send what was kept.
  useEffect(() => {
    if (!signedIn) return undefined;
    const go = () => void sendWaiting();
    window.addEventListener('online', go);
    return () => window.removeEventListener('online', go);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn]);

  const login = async () => {
    setBusy(true);
    setError('');
    try {
      const s = await tabletLogin(company, code.trim(), pin);
      sessionStorage.setItem(TOKEN_KEY, s.token);
      sessionStorage.setItem(NAME_KEY, s.operator.name);
      rememberTabletOperator(s.operator.id);
      setPin('');
      bump((n) => n + 1);
    } catch (err) {
      setError(tabletErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const act = async (card: JobCard, verb: TabletVerb) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const out = await tabletTap(card.id, verb, verb === 'report' || verb === 'finish' ? { qtyGood: good[card.id] || '0', qtyRejected: bad[card.id] || '0' } : undefined);
      setGood({ ...good, [card.id]: '' });
      setBad({ ...bad, [card.id]: '' });
      setWaiting(tabletQueue().length);
      if (out.queued) setNotice(t('mfg.tablet.saved'));
      else await load();
    } catch (err) {
      setError(tabletErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (!Number.isFinite(company) || company <= 0) {
    return (
      <Container maxWidth="sm" sx={{ py: 6 }}>
        <Alert severity="warning">{t('mfg.tablet.noCompany')}</Alert>
      </Container>
    );
  }

  if (!signedIn) {
    return (
      <Container maxWidth="xs" sx={{ py: 6 }}>
        <Stack spacing={3}>
          <Typography variant="h4" component="h1">{t('mfg.tablet.title')}</Typography>
          {error ? <Alert severity="error">{error}</Alert> : null}
          <TextField label={t('mfg.tablet.code')} value={code} onChange={(e) => setCode(e.target.value)} autoFocus inputProps={{ autoCapitalize: 'characters' }} />
          <TextField
            label={t('mfg.floor.pin')}
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
            inputProps={{ inputMode: 'numeric', maxLength: 8, autoComplete: 'off' }}
            onKeyDown={(e) => { if (e.key === 'Enter' && code && pin.length >= 4) void login(); }}
          />
          <Button size="large" variant="contained" disabled={busy || !code || pin.length < 4} onClick={login}>{t('mfg.tablet.signIn')}</Button>
        </Stack>
      </Container>
    );
  }

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h5" component="h1">{t('mfg.tablet.hello', { name })}</Typography>
          <Button onClick={signOut}>{t('mfg.tablet.signOut')}</Button>
        </Stack>
        {offline ? <Alert severity="warning">{t('mfg.tablet.offline')}</Alert> : null}
        {notice ? <Alert severity="info" onClose={() => setNotice('')}>{notice}</Alert> : null}
        {waiting > 0 ? (
          <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => void sendWaiting()}>{t('mfg.tablet.sendNow')}</Button>}>
            {t('mfg.tablet.waiting', { n: waiting })}
          </Alert>
        ) : null}
        {error || (cardsQuery.isError && !offline) ? <Alert severity="error" onClose={() => setError('')}>{error || tabletErrorMessage(cardsQuery.error)}</Alert> : null}
        {cards.length === 0 ? <Typography color="text.secondary">{t('mfg.tablet.nothing')}</Typography> : null}
        {cards.map((c) => (
          <Card key={c.id} variant="outlined">
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6">{c.workOrderNumber} · {c.name}</Typography>
                <Pill value={c.status} />
              </Stack>
              <Typography color="text.secondary">
                {c.workCentreCode} · {t('mfg.wo.good')} {qty(c.qtyGood)} / {qty(c.qtyPlanned)}
              </Typography>
              {['IN_PROGRESS', 'PAUSED'].includes(c.status) ? (
                <Box sx={{ pt: 2 }}>
                  <Stack direction="row" spacing={2}>
                    <NumField label={t('mfg.wo.good')} value={good[c.id] ?? ''} onChange={(v) => setGood({ ...good, [c.id]: v })} width={140} />
                    <NumField label={t('mfg.wo.rejected')} value={bad[c.id] ?? ''} onChange={(v) => setBad({ ...bad, [c.id]: v })} width={140} />
                  </Stack>
                </Box>
              ) : null}
            </CardContent>
            <CardActions sx={{ p: 2, gap: 1, flexWrap: 'wrap' }}>
              {['PLANNED', 'PAUSED'].includes(c.status) ? <Button size="large" variant="contained" disabled={busy} onClick={() => void act(c, 'start')}>{t('mfg.floor.start')}</Button> : null}
              {c.status === 'IN_PROGRESS' ? <Button size="large" variant="outlined" disabled={busy} onClick={() => void act(c, 'pause')}>{t('mfg.floor.pause')}</Button> : null}
              {['IN_PROGRESS', 'PAUSED'].includes(c.status) ? <Button size="large" disabled={busy} onClick={() => void act(c, 'report')}>{t('mfg.tablet.report')}</Button> : null}
              {['IN_PROGRESS', 'PAUSED'].includes(c.status) ? <Button size="large" color="success" variant="contained" disabled={busy} onClick={() => void act(c, 'finish')}>{t('mfg.floor.finish')}</Button> : null}
            </CardActions>
          </Card>
        ))}
      </Stack>
    </Container>
  );
}
