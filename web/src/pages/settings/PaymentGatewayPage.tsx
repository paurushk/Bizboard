import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '@/api/resources';
import type { GatewayKeyCheck, GatewaySettings } from '@/api/legacy/payments';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage, type SettingsBanner } from '@/components/settings/SettingsPage';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { settingsErrorText } from '@/utils/settingsErrors';

/** The credential fields each provider needs, in one place. Names match what the server reads. */
type KeyField = { name: string; label: string; secret?: boolean; options?: string[]; help?: string };
const KEY_FIELDS: Record<string, KeyField[]> = {
  razorpay: [
    { name: 'key_id', label: 'gateway.fieldKeyId' },
    { name: 'key_secret', label: 'gateway.fieldKeySecret', secret: true },
    { name: 'webhook_secret', label: 'gateway.fieldWebhookSecret', secret: true, help: 'gateway.webhookSecretHelp' },
  ],
  cashfree: [
    { name: 'app_id', label: 'gateway.fieldAppId' },
    { name: 'secret_key', label: 'gateway.fieldSecretKey', secret: true },
    { name: 'webhook_secret', label: 'gateway.fieldWebhookSecret', secret: true, help: 'gateway.webhookSecretHelp' },
    { name: 'api_base', label: 'gateway.fieldApiBase', options: ['https://api.cashfree.com/pg', 'https://sandbox.cashfree.com/pg'] },
  ],
  payu: [
    { name: 'merchant_key', label: 'gateway.fieldMerchantKey' },
    { name: 'merchant_salt', label: 'gateway.fieldMerchantSalt', secret: true },
    { name: 'api_base', label: 'gateway.fieldApiBase', options: ['https://secure.payu.in', 'https://test.payu.in'] },
  ],
  sandbox: [],
};

const PROVIDER_LABEL: Record<string, string> = {
  razorpay: 'Razorpay',
  cashfree: 'Cashfree',
  payu: 'PayU',
  sandbox: '',
};

function checkMessage(check: GatewayKeyCheck): { severity: 'success' | 'error' | 'warning' | 'info'; text: string } {
  const text = check.detail || t(`gateway.check.${check.status}`);
  if (check.status === 'valid') return { severity: 'success', text };
  if (check.status === 'invalid') return { severity: 'error', text };
  if (check.status === 'missing') return { severity: 'info', text };
  return { severity: 'warning', text };
}

export function PaymentGatewayPage() {
  const { writesBlocked } = useSubscriptionGate();
  const query = useQuery({ queryKey: ['gateway-settings'], queryFn: api.getGatewaySettings });
  return (
    <SettingsPage
      title={t('phase.paymentGateway')}
      purpose={t('gateway.purpose')}
    >
      <AsyncSection query={query}>
        {(settings) => <GatewayForm key={settings.provider} settings={settings} writesBlocked={writesBlocked} />}
      </AsyncSection>
    </SettingsPage>
  );
}

function GatewayForm({ settings, writesBlocked }: { settings: GatewaySettings; writesBlocked: boolean }) {
  const qc = useQueryClient();
  const [provider, setProvider] = useState(settings.provider || 'razorpay');
  const [testMode, setTestMode] = useState(Boolean(settings.testMode));
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<SettingsBanner | null>(null);
  const [check, setCheck] = useState<GatewayKeyCheck | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const fields = KEY_FIELDS[provider] ?? [];
  const typedKeys = fields.some((f) => (keys[f.name] ?? '').trim() !== '');
  const providerChanged = provider !== settings.provider;
  const testModeChanged = settings.testModeAvailable && testMode !== Boolean(settings.testMode);
  const dirty = typedKeys || providerChanged || testModeChanged;
  const refresh = () => void qc.invalidateQueries({ queryKey: ['gateway-settings'] });

  const save = useMutation({
    mutationFn: () => {
      const payload: Record<string, unknown> = { provider };
      if (settings.testModeAvailable) payload.test_mode = testMode;
      if (typedKeys) {
        // Only the fields this provider uses, and only the ones typed: a blank never wipes a saved key.
        payload.credentials = Object.fromEntries(
          fields.filter((f) => (keys[f.name] ?? '').trim() !== '').map((f) => [f.name, keys[f.name].trim()]),
        );
      }
      return api.updateGatewaySettings(payload);
    },
    onSuccess: () => {
      setKeys({});
      setCheck(null);
      setMessage({ severity: 'success', text: t('integrations.gatewaySaved') });
      refresh();
    },
    onError: (e) => setMessage({ severity: 'error', text: settingsErrorText(e) }),
  });

  const verify = useMutation({
    mutationFn: () => api.verifyGatewayKeys(),
    onSuccess: (result) => {
      setCheck(result);
      refresh();
    },
    onError: (e) => setMessage({ severity: 'error', text: settingsErrorText(e) }),
  });

  const remove = useMutation({
    mutationFn: () => api.updateGatewaySettings({ clear_credentials: true }),
    onSuccess: () => {
      setConfirmRemove(false);
      setCheck(null);
      setMessage({ severity: 'success', text: t('gateway.removed') });
      refresh();
    },
    onError: (e) => {
      setConfirmRemove(false);
      setMessage({ severity: 'error', text: settingsErrorText(e) });
    },
  });

  const providerKeysSaved = settings.credentialsConfigured && !providerChanged;
  const modeText =
    settings.credentialsMode === 'test'
      ? t('gateway.modeTest')
      : settings.credentialsMode === 'live'
        ? t('gateway.modeLive')
        : t('gateway.modeUnknown');

  return (
    <>
      {message ? (
        <Alert severity={message.severity} onClose={() => setMessage(null)}>
          {message.text}
        </Alert>
      ) : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <TextField
            select
            label={t('sweep.provider')}
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setKeys({});
            }}
          >
            {['razorpay', 'cashfree', 'payu', 'sandbox']
              .filter((p) => settings.enabledProviders.includes(p) || p === settings.provider)
              .map((p) => (
                <MenuItem key={p} value={p}>
                  {p === 'sandbox' ? t('sweep2.sandboxCiLocal') : PROVIDER_LABEL[p]}
                </MenuItem>
              ))}
          </TextField>

          {settings.testModeAvailable ? (
            <FormControlLabel
              control={<Switch checked={testMode} onChange={(e) => setTestMode(e.target.checked)} />}
              label={
                <Stack>
                  <span>{t('sweep.testMode')}</span>
                  <Typography variant="caption" color="text.secondary">
                    {t('gateway.testModeDevOnly')}
                  </Typography>
                </Stack>
              }
            />
          ) : null}

          {providerKeysSaved ? (
            <Alert severity={settings.credentialsVerified ? 'success' : 'info'}>
              {t('gateway.keysSaved', { hint: settings.credentialsHint || '—', mode: modeText })}{' '}
              {settings.credentialsVerified
                ? t('gateway.verifiedOn', {
                    date: settings.credentialsVerifiedAt ? new Date(settings.credentialsVerifiedAt).toLocaleString() : '',
                  })
                : settings.verificationSupported
                  ? t('gateway.notChecked')
                  : t('gateway.cannotCheck')}
            </Alert>
          ) : provider !== 'sandbox' ? (
            <Alert severity="warning">{t('integrations.paymentGatewayClosed')}</Alert>
          ) : null}

          {providerKeysSaved && settings.credentialsMode === 'test' && !settings.testModeAvailable ? (
            <Alert severity="warning">{t('gateway.testKeysWarning')}</Alert>
          ) : null}

          {fields.map((f) =>
            f.options ? (
              <TextField
                key={f.name}
                select
                label={t(f.label)}
                value={keys[f.name] ?? ''}
                onChange={(e) => setKeys({ ...keys, [f.name]: e.target.value })}
                helperText={t('gateway.apiBaseHelp')}
              >
                <MenuItem value="">{t('gateway.apiBaseDefault')}</MenuItem>
                {f.options.map((o) => (
                  <MenuItem key={o} value={o}>
                    {o}
                  </MenuItem>
                ))}
              </TextField>
            ) : (
              <TextField
                key={f.name}
                label={t(f.label)}
                type={f.secret ? 'password' : 'text'}
                value={keys[f.name] ?? ''}
                onChange={(e) => setKeys({ ...keys, [f.name]: e.target.value })}
                helperText={
                  f.help && !(f.name === 'webhook_secret' && settings.webhookSecretConfigured && !providerChanged)
                    ? t(f.help)
                    : providerKeysSaved
                      ? t('gateway.replaceKeyHelp')
                      : undefined
                }
                slotProps={{ htmlInput: { autoComplete: 'off' } }}
              />
            ),
          )}
          {providerKeysSaved && fields.some((f) => f.name === 'webhook_secret') ? (
            <Alert severity={settings.webhookSecretConfigured ? 'success' : 'warning'}>
              {settings.webhookSecretConfigured ? t('gateway.webhookSecretSaved') : t('gateway.webhookSecretMissing')}
            </Alert>
          ) : null}
          {providerKeysSaved ? (
            <Typography variant="body2" color="text.secondary">
              {settings.lastWebhookAt
                ? t('gateway.lastEvent', { date: new Date(settings.lastWebhookAt).toLocaleString() })
                : t('gateway.noEventYet')}
            </Typography>
          ) : null}

          {check ? <Alert severity={checkMessage(check).severity}>{checkMessage(check).text}</Alert> : null}

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button variant="contained" disabled={writesBlocked || save.isPending || !dirty} onClick={() => save.mutate()}>
              {t('sweep2.saveSettings')}
            </Button>
            {providerKeysSaved ? (
              <Button
                variant="outlined"
                disabled={writesBlocked || verify.isPending || dirty || !settings.verificationSupported}
                onClick={() => verify.mutate()}
              >
                {verify.isPending ? t('gateway.checking') : t('gateway.checkKeys')}
              </Button>
            ) : null}
            {providerKeysSaved ? (
              <Button color="error" disabled={writesBlocked || remove.isPending} onClick={() => setConfirmRemove(true)}>
                {t('gateway.removeKeys')}
              </Button>
            ) : null}
          </Stack>
          {providerKeysSaved && dirty ? (
            <Typography variant="caption" color="text.secondary">
              {t('gateway.saveBeforeCheck')}
            </Typography>
          ) : null}

          {Object.keys(settings.webhookPaths ?? {}).length > 0 ? (
            <Stack spacing={0.5}>
              <Typography variant="subtitle2">{t('sweep2.webhookUrls')}</Typography>
              {Object.entries(settings.webhookPaths).map(([name, path]) => (
                <Stack key={name} direction="row" spacing={1} alignItems="center">
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                    {name}: {path}
                  </Typography>
                  <Button
                    size="small"
                    onClick={() => void navigator.clipboard?.writeText(`${window.location.origin}${path}`)}
                  >
                    {t('gateway.copy')}
                  </Button>
                </Stack>
              ))}
            </Stack>
          ) : null}
        </Stack>
      </Paper>

      <ConfirmDialog
        open={confirmRemove}
        title={t('gateway.removeKeysTitle')}
        body={t('gateway.removeKeysBody')}
        confirmLabel={t('gateway.removeKeys')}
        confirmColor="error"
        confirming={remove.isPending}
        onClose={() => setConfirmRemove(false)}
        onConfirm={() => remove.mutate()}
      />
    </>
  );
}
