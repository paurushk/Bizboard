import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  confirmMfa,
  disableMfa,
  getMfaStatus,
  regenerateMfaRecoveryCodes,
  startMfaSetup,
  type MfaSetup,
} from '@/api/auth';
import { getErrorMessage } from '@/api/client';
import { t, useLocale } from '@/i18n';

const STATUS_KEY = ['mfa-status'];

/**
 * Per-user two-step verification (TOTP) enrolment, F-SEC-02. The server enforces nothing
 * until the user proves they can generate a code (confirm), then login requires it.
 * Recovery codes are shown once, right after confirm or regenerate.
 */
export function TwoStepVerificationPanel() {
  useLocale();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: getMfaStatus });
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [disabling, setDisabling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: STATUS_KEY });
  const fail = (err: unknown) => setError(getErrorMessage(err));

  const start = useMutation({
    mutationFn: startMfaSetup,
    onSuccess: (data) => {
      setError(null);
      setSetup(data);
      setCode('');
    },
    onError: fail,
  });
  const confirm = useMutation({
    mutationFn: () => confirmMfa(code.trim()),
    onSuccess: (codes) => {
      setError(null);
      setSetup(null);
      setCode('');
      setRecoveryCodes(codes);
      void refresh();
    },
    onError: fail,
  });
  const turnOff = useMutation({
    // Six digits is an authenticator code; anything longer is a recovery code, so someone who lost
    // their phone can still turn two-step verification off.
    mutationFn: () => disableMfa(password, code.trim().length === 6 ? { code: code.trim() } : { recoveryCode: code.trim() }),
    onSuccess: () => {
      setError(null);
      setDisabling(false);
      setPassword('');
      setCode('');
      void refresh();
    },
    onError: fail,
  });
  const regenerate = useMutation({
    mutationFn: () => regenerateMfaRecoveryCodes(password, code.trim()),
    onSuccess: (codes) => {
      setError(null);
      setRecoveryCodes(codes);
      setPassword('');
      setCode('');
      void refresh();
    },
    onError: fail,
  });

  const enabled = Boolean(status.data?.enabled);

  return (
    <Paper sx={{ p: 2 }} component="section" aria-label={t('auth.mfa.panelTitle')}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="h6" component="h2">
            {t('auth.mfa.panelTitle')}
          </Typography>
          {status.data ? (
            <Chip
              size="small"
              color={enabled ? 'success' : 'default'}
              label={enabled ? t('auth.mfa.statusOn') : t('auth.mfa.statusOff')}
            />
          ) : null}
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {t('auth.mfa.panelIntro')}
        </Typography>
        {error ? <Alert severity="error">{error}</Alert> : null}

        {recoveryCodes ? (
          <Stack spacing={1}>
            <Typography fontWeight={600}>{t('auth.mfa.recoveryTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('auth.mfa.recoveryHelp')}
            </Typography>
            <Box
              component="ul"
              aria-label={t('auth.mfa.recoveryTitle')}
              sx={{ m: 0, p: 1.5, listStyle: 'none', bgcolor: 'action.hover', borderRadius: 1, fontFamily: 'monospace', columnCount: 2 }}
            >
              {recoveryCodes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </Box>
            <Box>
              <Button variant="contained" onClick={() => setRecoveryCodes(null)}>
                {t('auth.mfa.recoveryDone')}
              </Button>
            </Box>
          </Stack>
        ) : null}

        {!recoveryCodes && setup ? (
          <Stack spacing={1.5}>
            <Typography variant="body2">{t('auth.mfa.scanHelp')}</Typography>
            <Box component="img" src={setup.qrPng} alt="" sx={{ width: 180, height: 180, alignSelf: 'flex-start' }} />
            <Typography variant="body2">
              {t('auth.mfa.manualKey')}: <code>{setup.secret}</code>
            </Typography>
            <TextField
              label={t('auth.mfa.enterCode')}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoComplete="one-time-code"
              slotProps={{ htmlInput: { inputMode: 'numeric', pattern: '[0-9]*', maxLength: 6 } }}
              sx={{ maxWidth: 260 }}
            />
            <Stack direction="row" spacing={1}>
              <Button variant="contained" disabled={code.trim().length !== 6 || confirm.isPending} onClick={() => confirm.mutate()}>
                {t('auth.mfa.confirm')}
              </Button>
              <Button onClick={() => { setSetup(null); setError(null); }}>{t('auth.mfa.cancel')}</Button>
            </Stack>
          </Stack>
        ) : null}

        {!recoveryCodes && !setup && status.data && !enabled ? (
          <Box>
            <Button variant="contained" disabled={start.isPending} onClick={() => start.mutate()}>
              {t('auth.mfa.enable')}
            </Button>
          </Box>
        ) : null}

        {!recoveryCodes && !setup && enabled ? (
          <Stack spacing={1.5}>
            <Typography variant="body2">
              {t('auth.mfa.remaining', { n: status.data?.recoveryCodesRemaining ?? 0 })}
            </Typography>
            {disabling ? (
              <Stack spacing={1.5}>
                <Typography variant="body2" color="text.secondary">
                  {t('auth.mfa.disableHelp')}
                </Typography>
                <TextField
                  label={t('auth.mfa.passwordLabel')}
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  sx={{ maxWidth: 320 }}
                />
                <TextField
                  label={`${t('auth.mfa.codeLabel')} / ${t('auth.mfa.recoveryLabel')}`}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoComplete="one-time-code"
                  slotProps={{ htmlInput: { maxLength: 32 } }}
                  sx={{ maxWidth: 260 }}
                />
                <Stack direction="row" spacing={1}>
                  <Button
                    color="error"
                    variant="contained"
                    disabled={!password || code.trim().length < 6 || turnOff.isPending}
                    onClick={() => turnOff.mutate()}
                  >
                    {t('auth.mfa.disable')}
                  </Button>
                  <Button
                    variant="outlined"
                    disabled={!password || code.trim().length !== 6 || regenerate.isPending}
                    onClick={() => regenerate.mutate()}
                  >
                    {t('auth.mfa.regenerate')}
                  </Button>
                  <Button onClick={() => { setDisabling(false); setError(null); setPassword(''); setCode(''); }}>
                    {t('auth.mfa.cancel')}
                  </Button>
                </Stack>
              </Stack>
            ) : (
              <Box>
                <Button variant="outlined" onClick={() => setDisabling(true)}>
                  {t('auth.mfa.disable')} / {t('auth.mfa.regenerate')}
                </Button>
              </Box>
            )}
          </Stack>
        ) : null}
      </Stack>
    </Paper>
  );
}
