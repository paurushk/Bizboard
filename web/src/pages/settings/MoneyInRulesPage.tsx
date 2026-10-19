import Alert from '@mui/material/Alert';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as api from '@/api/resources';
import type { MoneyInRules } from '@/api/legacy/payments';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { SettingsSaveBar } from '@/components/settings/SettingsSaveBar';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useSettingsForm } from '@/hooks/useSettingsForm';
import { t } from '@/i18n';
import { confirmAction } from '@/utils/confirmBridge';
import { confirmWithPreview } from '@/utils/settingsPreview';
import { savedStamp } from '@/utils/settingsStamp';
import { settingsErrorText } from '@/utils/settingsErrors';

/**
 * SET-05: how receipts are recorded and matched. These rules used to sit on the payment gateway
 * screen; they have their own endpoint and their own Save, so changing a cash rule can never touch
 * the gateway keys.
 */
export function MoneyInRulesPage() {
  const query = useQuery({ queryKey: ['money-in-rules'], queryFn: api.getMoneyInRules });
  return (
    <SettingsPage
      title={t('moneyInRules.title')}
      purpose={t('moneyInRules.purpose')}
    >
      <AsyncSection query={query}>
        {(rules) => (
          <>
            <RulesForm initial={rules} />
            <CollectionsForm initial={rules} />
          </>
        )}
      </AsyncSection>
    </SettingsPage>
  );
}

function RulesForm({ initial }: { initial: MoneyInRules }) {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const form = useSettingsForm<MoneyInRules, { updatedAt?: string | null }>({
    initial,
    initialUpdatedAt: initial.updatedAt ?? null,
    refetch: async () => {
      const latest = await api.getMoneyInRules();
      qc.setQueryData(['money-in-rules'], latest);
      return { values: latest, updatedAt: latest.updatedAt ?? null };
    },
    save: async (values, ctx) => {
      if (values.cash269stMode !== initial.cash269stMode) {
        const agreed = await confirmWithPreview(
          'cash_269st',
          { cash_269st_mode: values.cash269stMode },
          t('settingsPreview.cash_confirm'),
        );
        if (!agreed) throw new Error(t('gstPage.cancelled'));
      }
      const stamp = savedStamp(qc, ['money-in-rules'], ctx.expectedUpdatedAt, initial.updatedAt);
      await api.updateMoneyInRules({
        ...(stamp ? { expected_updated_at: stamp } : {}),
        require_payment_reference: values.requirePaymentReference,
        auto_match_bank_exact: values.autoMatchBankExact,
        cheque_allocation_on_clearance: values.chequeAllocationOnClearance,
        cash_269st_mode: values.cash269stMode,
        advance_gst_treatment: values.advanceGstTreatment,
        advance_gst_default_rate:
          values.advanceGstTreatment === 'services' && (values.advanceGstDefaultRate ?? '').trim() !== ''
            ? values.advanceGstDefaultRate
            : null,
      });
      await qc.invalidateQueries({ queryKey: ['money-in-rules'] });
      return {};
    },
  });
  const v = form.values;
  const set = (patch: Partial<MoneyInRules>) => form.setValues({ ...v, ...patch });

  return (
    <>
      {form.error ? <Alert severity="error">{settingsErrorText(form.error)}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <FormControlLabel
            control={
              <Switch
                checked={v.requirePaymentReference}
                onChange={(e) => set({ requirePaymentReference: e.target.checked })}
              />
            }
            label={t('sweep.requireUtr')}
          />
          <FormControlLabel
            control={
              <Switch checked={v.autoMatchBankExact} onChange={(e) => set({ autoMatchBankExact: e.target.checked })} />
            }
            label={t('sweep.autoMatchUtr')}
          />
          <FormControlLabel
            control={
              <Switch
                checked={v.chequeAllocationOnClearance}
                onChange={(e) => set({ chequeAllocationOnClearance: e.target.checked })}
              />
            }
            label={t('receipts.policyChequeOnClear')}
          />
          <Typography variant="caption" color="text.secondary">
            {t('receipts.policyChequeOnClearHelp')}
          </Typography>
          <TextField
            select
            label={t('receipts.policyCash269st')}
            value={v.cash269stMode}
            onChange={(e) => set({ cash269stMode: e.target.value as MoneyInRules['cash269stMode'] })}
            helperText={t('receipts.policyCash269stHelp')}
          >
            <MenuItem value="off">{t('receipts.policyCashOff')}</MenuItem>
            <MenuItem value="warn">{t('receipts.policyCashWarn')}</MenuItem>
            <MenuItem value="block">{t('receipts.policyCashBlock')}</MenuItem>
          </TextField>
          <TextField
            select
            label={t('receipts.policyAdvanceGst')}
            value={v.advanceGstTreatment}
            onChange={(e) => set({ advanceGstTreatment: e.target.value as MoneyInRules['advanceGstTreatment'] })}
            helperText={t('receipts.policyAdvanceGstHelp')}
          >
            <MenuItem value="none">{t('receipts.policyAdvanceNone')}</MenuItem>
            <MenuItem value="goods">{t('receipts.policyAdvanceGoods')}</MenuItem>
            <MenuItem value="services">{t('receipts.policyAdvanceServices')}</MenuItem>
          </TextField>
          {v.advanceGstTreatment === 'services' ? (
            <TextField
              type="number"
              label={t('receipts.policyAdvanceRate')}
              value={v.advanceGstDefaultRate ?? ''}
              onChange={(e) => set({ advanceGstDefaultRate: e.target.value })}
              slotProps={{ htmlInput: { min: 0, max: 40, step: '0.01' } }}
            />
          ) : null}
        </Stack>
      </Paper>
      <SettingsSaveBar form={form} disabled={writesBlocked} sticky={false} />
    </>
  );
}

type Collections = {
  dunningEnabled: boolean;
  dunningDaysText: string;
  dunningMaxReminders: number;
  dunningQuietHoursStart: number;
  dunningQuietHoursEnd: number;
  autoCreditHoldOnSevereOverdue: boolean;
};

function parseDays(text: string): number[] {
  return text
    .split(/[,\s]+/)
    .filter(Boolean)
    .map((p) => Number(p));
}

/** SET-17: payment reminders and the automatic credit hold. Own section, own Save. */
function CollectionsForm({ initial }: { initial: MoneyInRules }) {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const form = useSettingsForm<Collections, { updatedAt?: string | null }>({
    initial: {
      dunningEnabled: initial.dunningEnabled,
      dunningDaysText: (initial.dunningDays ?? []).join(', '),
      dunningMaxReminders: initial.dunningMaxReminders,
      dunningQuietHoursStart: initial.dunningQuietHoursStart,
      dunningQuietHoursEnd: initial.dunningQuietHoursEnd,
      autoCreditHoldOnSevereOverdue: initial.autoCreditHoldOnSevereOverdue,
    },
    initialUpdatedAt: initial.updatedAt ?? null,
    refetch: async () => {
      const latest = await api.getMoneyInRules();
      qc.setQueryData(['money-in-rules'], latest);
      return {
        values: {
          dunningEnabled: latest.dunningEnabled,
          dunningDaysText: (latest.dunningDays ?? []).join(', '),
          dunningMaxReminders: latest.dunningMaxReminders,
          dunningQuietHoursStart: latest.dunningQuietHoursStart,
          dunningQuietHoursEnd: latest.dunningQuietHoursEnd,
          autoCreditHoldOnSevereOverdue: latest.autoCreditHoldOnSevereOverdue,
        },
        updatedAt: latest.updatedAt ?? null,
      };
    },
    save: async (values, ctx) => {
      const days = parseDays(values.dunningDaysText);
      if (days.some((n) => !Number.isInteger(n) || n < 1 || n > 365)) {
        throw new Error(t('collections.daysInvalid'));
      }
      const stamp = savedStamp(qc, ['money-in-rules'], ctx.expectedUpdatedAt, initial.updatedAt);
      await api.updateMoneyInRules({
        ...(stamp ? { expected_updated_at: stamp } : {}),
        dunning_enabled: values.dunningEnabled,
        dunning_days: days,
        dunning_max_reminders: values.dunningMaxReminders,
        dunning_quiet_hours_start: values.dunningQuietHoursStart,
        dunning_quiet_hours_end: values.dunningQuietHoursEnd,
        auto_credit_hold_on_severe_overdue: values.autoCreditHoldOnSevereOverdue,
      });
      await qc.invalidateQueries({ queryKey: ['money-in-rules'] });
      void qc.invalidateQueries({ queryKey: ['company'] });
      return {};
    },
  });
  const v = form.values;
  const set = (patch: Partial<Collections>) => form.setValues({ ...v, ...patch });
  // Turning reminders on is a standing rule that messages customers: say so, and show the schedule.
  const guarded = {
    ...form,
    save: async () => {
      if (v.dunningEnabled && !initial.dunningEnabled) {
        const days = parseDays(v.dunningDaysText).filter((n) => Number.isFinite(n) && n >= 1);
        if (!(await confirmAction(t('settings.dunningConfirm', { days: days.join(', ') || '—' })))) return undefined;
      }
      return form.save();
    },
  };

  return (
    <>
      <Typography variant="h6" component="h2" sx={{ pt: 2 }}>
        {t('collections.title')}
      </Typography>
      {form.error ? <Alert severity="error">{settingsErrorText(form.error)}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {t('settings.dunningHelp')}
          </Typography>
          <FormControlLabel
            control={<Switch checked={v.dunningEnabled} onChange={(e) => set({ dunningEnabled: e.target.checked })} />}
            label={t('settings.dunningEnabled')}
          />
          <TextField
            label={t('settings.dunningDays')}
            helperText={t('settings.dunningDaysHelp')}
            value={v.dunningDaysText}
            onChange={(e) => set({ dunningDaysText: e.target.value })}
          />
          <TextField
            type="number"
            label={t('settings.dunningMaxReminders')}
            value={v.dunningMaxReminders}
            onChange={(e) => set({ dunningMaxReminders: Number(e.target.value) })}
            slotProps={{ htmlInput: { min: 1, max: 10 } }}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              type="number"
              label={t('settings.dunningQuietStart')}
              value={v.dunningQuietHoursStart}
              onChange={(e) => set({ dunningQuietHoursStart: Number(e.target.value) })}
              slotProps={{ htmlInput: { min: 0, max: 23 } }}
            />
            <TextField
              type="number"
              label={t('settings.dunningQuietEnd')}
              value={v.dunningQuietHoursEnd}
              onChange={(e) => set({ dunningQuietHoursEnd: Number(e.target.value) })}
              slotProps={{ htmlInput: { min: 0, max: 23 } }}
            />
          </Stack>
          <FormControlLabel
            control={
              <Switch
                checked={v.autoCreditHoldOnSevereOverdue}
                onChange={(e) => set({ autoCreditHoldOnSevereOverdue: e.target.checked })}
              />
            }
            label={t('settings.autoCreditHold')}
          />
          <Typography variant="body2" color="text.secondary">
            {t('settings.autoCreditHoldHelp')}
          </Typography>
        </Stack>
      </Paper>
      <SettingsSaveBar form={guarded} disabled={writesBlocked} />
    </>
  );
}
