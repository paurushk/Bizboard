import { useState, type ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getCompany, updateCompany, verifyCompanyGstin, verifyCompanyPan, verifyCompanyUdyam } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { SettingsErrorAlert } from '@/components/settings/SettingsErrorAlert';
import { SettingsSaveBar } from '@/components/settings/SettingsSaveBar';
import { StateSelect } from '@/components/StateSelect';
import { useSettingsForm, type SettingsForm } from '@/hooks/useSettingsForm';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { HelpHint } from '@/pages/help/HelpHint';
import { BranchGstinsPanel } from '@/pages/settings/BranchGstinsPanel';
import type { Company, NegativeStockPolicy, RegistrationType } from '@/types/domain';
import { confirmWithPreview } from '@/utils/settingsPreview';
import { isValidGstin } from '@/utils/gst';
import { canManageGst } from '@/utils/permissions';
import { savedStamp } from '@/utils/settingsStamp';

/**
 * SET-16: the GST page in four sections, each with its own Save, so a change to the e-invoice
 * switch can never carry along a half-edited GSTIN or the portal keys. All four write to the
 * company record, but each sends only its own fields.
 */
export function GstSettingsPage() {
  const { user } = useAuth();
  // F3-014: no refetch-and-reset on window focus, which would wipe unsaved edits.
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany, refetchOnWindowFocus: false });
  if (!canManageGst(user)) return <ForbiddenPage />;
  return (
    <SettingsPage
      title={t('nav.gst')}
      purpose={t('gstPage.purpose')}
    >
      <AsyncSection query={query}>
        {(company) => (
          <>
            <RegistrationSection company={company} />
            <BranchGstinsPanel />
            <StockRulesSection company={company} />
            <EinvoiceSection company={company} />
          </>
        )}
      </AsyncSection>
    </SettingsPage>
  );
}

function Section<TValues extends object>({
  title,
  help,
  form,
  children,
}: {
  title: string;
  help?: string;
  form: SettingsForm<TValues, { updatedAt?: string | null }>;
  children: ReactNode;
}) {
  const { writesBlocked } = useSubscriptionGate();
  return (
    <Paper variant="outlined" sx={{ p: 3, maxWidth: 640 }} component="section" aria-label={title}>
      <Stack spacing={2}>
        <Typography variant="h6" component="h2" fontWeight={600}>
          {title}
        </Typography>
        {help ? (
          <Typography variant="body2" color="text.secondary">
            {help}
          </Typography>
        ) : null}
        {form.error ? <SettingsErrorAlert error={form.error} /> : null}
        {children}
        <SettingsSaveBar form={form} disabled={writesBlocked} sticky={false} />
      </Stack>
    </Paper>
  );
}

// ---- 1. Registration -------------------------------------------------------------------------

interface RegistrationForm {
  gstin: string;
  pan: string;
  udyam: string;
  state: string;
  registrationType: RegistrationType;
}

function RegistrationSection({ company }: { company: Company }) {
  const qc = useQueryClient();
  const [gstConfirmed, setGstConfirmed] = useState(false);
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const form = useSettingsForm<RegistrationForm, { updatedAt?: string | null }>({
    initial: {
      gstin: company.gstin ?? '',
      pan: company.pan ?? '',
      udyam: company.udyam ?? '',
      state: company.state ?? '',
      registrationType: company.registrationType ?? 'REGULAR',
    },
    initialUpdatedAt: company.updatedAt ?? null,
    refetch: async () => {
      const latest = await getCompany();
      qc.setQueryData(['company'], latest);
      return {
        values: {
          gstin: latest.gstin ?? '',
          pan: latest.pan ?? '',
          udyam: latest.udyam ?? '',
          state: latest.state ?? '',
          registrationType: latest.registrationType ?? 'REGULAR',
        },
        updatedAt: latest.updatedAt ?? null,
      };
    },
    save: async (values, ctx) => {
      const gstin = values.gstin.trim().toUpperCase();
      if (gstin && !isValidGstin(gstin)) throw new Error(t('gstPage.gstinInvalid'));
      // Only a new or changed GSTIN needs the confirmation; a blocked save says why.
      if (gstin && gstin !== (company.gstin ?? '').trim().toUpperCase() && !gstConfirmed) {
        setNeedsConfirm(true);
        throw new Error(t('cog.gstConfirm'));
      }
      setNeedsConfirm(false);
      if (values.registrationType !== (company.registrationType ?? 'REGULAR')) {
        const agreed = await confirmWithPreview(
          'gst_registration',
          { registration_type: values.registrationType, gstin },
          t('gst.confirmRegistrationChange', { type: values.registrationType }),
        );
        if (!agreed) throw new Error(t('gstPage.cancelled'));
      }
      // These are CharFields without null=True: send '' rather than null.
      const stamp = savedStamp(qc, ['company'], ctx.expectedUpdatedAt, company.updatedAt);
      await updateCompany({
        gstin,
        pan: values.pan.trim().toUpperCase(),
        udyam: values.udyam.trim().toUpperCase(),
        state: values.state,
        registrationType: values.registrationType,
        // The tick is recorded on the server (tax profile confirmed at), not just kept on this page.
        ...(gstin && gstin !== (company.gstin ?? '').trim().toUpperCase() ? { confirm_tax_profile: true } : {}),
        ...(stamp ? { expected_updated_at: stamp } : {}),
      } as never);
      await qc.invalidateQueries({ queryKey: ['company'] });
      void qc.invalidateQueries({ queryKey: ['company-gstins'] });
      return {};
    },
  });
  const v = form.values;
  const set = (patch: Partial<RegistrationForm>) => form.setValues({ ...v, ...patch });

  const verifyGstin = useMutation({
    mutationFn: async () => {
      if (!(company.gstin ?? '').trim()) throw new Error(t('gstPage.saveGstinFirst'));
      return verifyCompanyGstin();
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['company'] }),
  });
  const verifyPan = useMutation({
    mutationFn: verifyCompanyPan,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['company'] }),
  });
  const verifyUdyam = useMutation({
    mutationFn: verifyCompanyUdyam,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['company'] }),
  });
  const gstinChanged = v.gstin.trim().toUpperCase() !== (company.gstin ?? '').trim().toUpperCase();

  return (
    <Section title={t('gstPage.registrationTitle')} help={t('gstPage.registrationHelp')} form={form}>
      {verifyGstin.isSuccess ? (
        <Alert severity="info">
          {t('gst.verifyStatus', {
            status: verifyGstin.data?.status ?? t('gst.verified'),
            name: verifyGstin.data?.tradeName || t('gst.active'),
          })}
        </Alert>
      ) : null}
      {verifyGstin.isError ? <HelpErrorAlert error={verifyGstin.error} /> : null}
      <HelpHint intent="add-gstin" slot="gstin">
        <TextField
          label={t('gstSettings.primaryGstin')}
          placeholder="07AAAAA0000A1Z5"
          helperText={company.gstinVerificationStatus || t('gstPage.gstinBlankHelp')}
          value={v.gstin}
          onChange={(e) => set({ gstin: e.target.value })}
          fullWidth
        />
      </HelpHint>
      <Button
        variant="outlined"
        size="small"
        disabled={verifyGstin.isPending || !company.gstin || gstinChanged}
        onClick={() => verifyGstin.mutate()}
      >
        {t('sweep2.verifyGstin')}
      </Button>
      <TextField
        label={t('gstSettings.pan')}
        placeholder="ABCDE1234F"
        helperText={company.panVerificationStatus || t('gstPage.panHelp')}
        value={v.pan}
        onChange={(e) => set({ pan: e.target.value })}
      />
      <Button
        variant="outlined"
        size="small"
        disabled={verifyPan.isPending || !company.pan || v.pan !== (company.pan ?? '')}
        onClick={() => verifyPan.mutate()}
      >
        {t('sweep2.verifyPan')}
      </Button>
      {verifyPan.isError ? <HelpErrorAlert error={verifyPan.error} /> : null}
      <TextField
        label={t('gstSettings.udyam')}
        placeholder="UDYAM-KR-00-0000000"
        helperText={company.udyamVerificationStatus || t('gstPage.udyamHelp')}
        value={v.udyam}
        onChange={(e) => set({ udyam: e.target.value })}
      />
      <Button
        variant="outlined"
        size="small"
        disabled={verifyUdyam.isPending || !company.udyam || v.udyam !== (company.udyam ?? '')}
        onClick={() => verifyUdyam.mutate()}
      >
        {t('sweep2.verifyUdyam')}
      </Button>
      {verifyUdyam.isError ? <HelpErrorAlert error={verifyUdyam.error} /> : null}
      <StateSelect value={v.state} onChange={(next: string) => set({ state: next })} />
      <HelpHint intent="registration-type" slot="registration-type-settings">
        <TextField
          select
          fullWidth
          label={t('gstSettings.registrationType')}
          value={v.registrationType}
          onChange={(e) => set({ registrationType: e.target.value as RegistrationType })}
        >
          <MenuItem value="REGULAR">{t('gstSettings.regular')}</MenuItem>
          <MenuItem value="COMPOSITION">{t('gstSettings.composition')}</MenuItem>
          <MenuItem value="UNREGISTERED">{t('gstSettings.unregistered')}</MenuItem>
        </TextField>
      </HelpHint>
      {gstinChanged && v.gstin.trim() ? (
        <>
          <FormControlLabel
            control={<Checkbox checked={gstConfirmed} onChange={(_, c) => setGstConfirmed(c)} />}
            label={t('cog.gstConfirm')}
          />
          {needsConfirm && !gstConfirmed ? <Alert severity="warning">{t('cog.gstConfirm')}</Alert> : null}
        </>
      ) : null}
    </Section>
  );
}

// ---- 2. Stock and tax rules ------------------------------------------------------------------

interface StockForm {
  negativeStockPolicy: NegativeStockPolicy;
  valuationBusinessDateOrder: boolean;
  recomputeTaxOnComplete: boolean;
  assumeLocalStateForBlankParty: boolean;
}

function StockRulesSection({ company }: { company: Company }) {
  const qc = useQueryClient();
  const initial: StockForm = {
    negativeStockPolicy: company.negativeStockPolicy ?? 'BLOCK',
    valuationBusinessDateOrder: !!company.valuationBusinessDateOrder,
    recomputeTaxOnComplete: !!company.recomputeTaxOnComplete,
    assumeLocalStateForBlankParty: !!company.assumeLocalStateForBlankParty,
  };
  const form = useSettingsForm<StockForm, { updatedAt?: string | null }>({
    initial,
    initialUpdatedAt: company.updatedAt ?? null,
    refetch: async () => {
      const latest = await getCompany();
      qc.setQueryData(['company'], latest);
      return {
        values: {
          negativeStockPolicy: latest.negativeStockPolicy ?? 'BLOCK',
          valuationBusinessDateOrder: !!latest.valuationBusinessDateOrder,
          recomputeTaxOnComplete: !!latest.recomputeTaxOnComplete,
          assumeLocalStateForBlankParty: !!latest.assumeLocalStateForBlankParty,
        },
        updatedAt: latest.updatedAt ?? null,
      };
    },
    save: async (values, ctx) => {
      const policyChanged = values.negativeStockPolicy !== initial.negativeStockPolicy;
      const rulesChanged =
        values.valuationBusinessDateOrder !== initial.valuationBusinessDateOrder ||
        values.recomputeTaxOnComplete !== initial.recomputeTaxOnComplete;
      if (policyChanged || rulesChanged) {
        const agreed = await confirmWithPreview(
          'stock_rules',
          {
            negative_stock_policy: values.negativeStockPolicy,
            valuation_business_date_order: values.valuationBusinessDateOrder,
            recompute_tax_on_complete: values.recomputeTaxOnComplete,
          },
          policyChanged
            ? t('gst.confirmNegativeStockChange', { policy: values.negativeStockPolicy })
            : t('settingsPreview.stock_confirm'),
        );
        if (!agreed) throw new Error(t('gstPage.cancelled'));
      }
      const stamp = savedStamp(qc, ['company'], ctx.expectedUpdatedAt, company.updatedAt);
      await updateCompany({ ...values, ...(stamp ? { expected_updated_at: stamp } : {}) } as never);
      await qc.invalidateQueries({ queryKey: ['company'] });
      return {};
    },
  });
  const v = form.values;
  const set = (patch: Partial<StockForm>) => form.setValues({ ...v, ...patch });
  const check = (key: 'valuationBusinessDateOrder' | 'recomputeTaxOnComplete' | 'assumeLocalStateForBlankParty', label: string, help?: string) => (
    <>
      <FormControlLabel
        control={<Checkbox checked={v[key]} onChange={(_, c) => set({ [key]: c })} />}
        label={label}
      />
      {help ? (
        <Typography variant="caption" color="text.secondary">
          {help}
        </Typography>
      ) : null}
    </>
  );
  return (
    <Section title={t('gstPage.stockTitle')} help={t('gstPage.stockHelp')} form={form}>
      <TextField
        select
        fullWidth
        label={t('gstSettings.stockPolicy')}
        helperText={t('gstSettings.stockPolicyHint')}
        value={v.negativeStockPolicy}
        onChange={(e) => set({ negativeStockPolicy: e.target.value as NegativeStockPolicy })}
      >
        <MenuItem value="BLOCK">{t('gstSettings.blockBilling')}</MenuItem>
        <MenuItem value="WARN">{t('gstSettings.allowWarn')}</MenuItem>
      </TextField>
      {check('valuationBusinessDateOrder', t('settings.valuationDateOrder'), t('settings.valuationDateOrderHelp'))}
      {check('recomputeTaxOnComplete', t('settings.recomputeTaxOnComplete'), t('settings.recomputeTaxOnCompleteHelp'))}
      {check('assumeLocalStateForBlankParty', t('gst.assumeLocalState'))}
    </Section>
  );
}

// ---- 3. e-Invoice and e-way bill -------------------------------------------------------------

/** One read-only line: a state Bizboard controls, shown so the owner can see where they stand. */
function StatusLine({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" spacing={1} justifyContent="space-between">
      <Typography variant="body2">{label}</Typography>
      <Typography variant="body2" fontWeight={600}>
        {value}
      </Typography>
    </Stack>
  );
}

interface EwayForm {
  ewayThresholdAmount: string;
}

/**
 * e-Invoice, e-way bill and the portal connection are switched on per company by Bizboard once the
 * registration is verified, and the company API ignores them from an owner. Showing a working
 * switch here used to say "saved" while changing nothing, so they are status only; the e-way
 * threshold is the one value an owner can change.
 */
function EinvoiceSection({ company }: { company: Company }) {
  const qc = useQueryClient();
  const form = useSettingsForm<EwayForm, { updatedAt?: string | null }>({
    initial: { ewayThresholdAmount: String(company.ewayThresholdAmount ?? '50000') },
    initialUpdatedAt: company.updatedAt ?? null,
    refetch: async () => {
      const latest = await getCompany();
      qc.setQueryData(['company'], latest);
      return { values: { ewayThresholdAmount: String(latest.ewayThresholdAmount ?? '50000') }, updatedAt: latest.updatedAt ?? null };
    },
    save: async (values, ctx) => {
      const amount = Number(values.ewayThresholdAmount);
      if (!Number.isFinite(amount) || amount < 0) throw new Error(t('gstPage.thresholdInvalid'));
      const stamp = savedStamp(qc, ['company'], ctx.expectedUpdatedAt, company.updatedAt);
      await updateCompany({ eway_threshold_amount: String(amount), ...(stamp ? { expected_updated_at: stamp } : {}) } as never);
      await qc.invalidateQueries({ queryKey: ['company'] });
      return {};
    },
  });
  const onOff = (on: boolean) => (on ? t('gstPage.statusOn') : t('gstPage.statusOff'));
  return (
    <Section title={t('gstPage.einvoiceTitle')} help={t('gstPage.einvoiceHelp')} form={form}>
      <Stack spacing={0.5}>
        <StatusLine label={t('gstSettings.einvoice')} value={onOff(!!company.einvoiceEnabled)} />
        <StatusLine label={t('gstSettings.eway')} value={onOff(!!company.ewayEnabled)} />
        <StatusLine label={t('gstSettings.turnover')} value={String(company.aatoTurnover ?? '') || '—'} />
        <StatusLine
          label={t('gstSettings.gspProvider')}
          value={company.gspProvider ? String(company.gspProvider) : t('gstSettings.gspManual')}
        />
        <StatusLine
          label={t('gstSettings.gspTitle')}
          value={company.gspCredentialsConfigured ? t('gstSettings.gspActive') : t('gstSettings.gspNone')}
        />
      </Stack>
      <Alert severity="info">{t('gstPage.controlledByBizboard')}</Alert>
      <TextField
        label={t('gstSettings.ewayThreshold')}
        helperText={t('gstSettings.ewayThresholdHint')}
        value={form.values.ewayThresholdAmount}
        onChange={(e) => form.setValues({ ewayThresholdAmount: e.target.value })}
      />
    </Section>
  );
}
