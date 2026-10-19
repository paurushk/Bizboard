import Alert from '@mui/material/Alert';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getCompany, updateCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { LogoPanel } from '@/components/settings/LogoPanel';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { SettingsSaveBar } from '@/components/settings/SettingsSaveBar';
import { StateSelect } from '@/components/StateSelect';
import { useSettingsForm } from '@/hooks/useSettingsForm';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { InvoiceBankSummary } from '@/pages/settings/InvoiceBankSummary';
import type { Company } from '@/types/domain';
import { canManageUsers } from '@/utils/permissions';
import { savedStamp } from '@/utils/settingsStamp';
import { isValidIndianPincode } from '@/utils/pincode';
import { settingsErrorText } from '@/utils/settingsErrors';

/** SET-17: who the business is. Money rules live on Bank Accounts and Money-In rules. */
interface IdentityForm {
  name: string;
  legalName: string;
  address: string;
  city: string;
  state: string;
  pincode: string;
  phone: string;
  email: string;
}

function toForm(c: Company): IdentityForm {
  return {
    name: c.name ?? '',
    legalName: c.legalName ?? '',
    address: c.address ?? '',
    city: c.city ?? '',
    state: c.state ?? '',
    pincode: c.pincode ?? '',
    phone: c.phone ?? '',
    email: c.email ?? '',
  };
}

export function CompanySettingsPage() {
  const { user } = useAuth();
  // F3-014: no refetch on window focus, which would reset unsaved edits.
  const query = useQuery({ queryKey: ['company'], queryFn: getCompany, refetchOnWindowFocus: false });
  if (!canManageUsers(user)) return <ForbiddenPage />;
  return (
    <SettingsPage
      title={t('nav.company')}
      purpose={t('companyPage.purpose')}
    >
      <AsyncSection query={query}>{(company) => <IdentityEditor company={company} />}</AsyncSection>
    </SettingsPage>
  );
}

function IdentityEditor({ company }: { company: Company }) {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const form = useSettingsForm<IdentityForm, { updatedAt?: string | null }>({
    initial: toForm(company),
    initialUpdatedAt: company.updatedAt ?? null,
    save: async (values, ctx) => {
      const pin = values.pincode.trim();
      if (pin !== (company.pincode ?? '').trim() && !isValidIndianPincode(pin)) {
        throw new Error(t('validation.pincode'));
      }
      if (!values.name.trim()) throw new Error(t('companyPage.nameRequired'));
      const stamp = savedStamp(qc, ['company'], ctx.expectedUpdatedAt, company.updatedAt);
      await updateCompany({ ...values, name: values.name.trim(), pincode: pin, ...(stamp ? { expected_updated_at: stamp } : {}) } as never);
      await qc.invalidateQueries({ queryKey: ['company'] });
      return {};
    },
    refetch: async () => {
      const latest = await getCompany();
      qc.setQueryData(['company'], latest);
      return { values: toForm(latest), updatedAt: latest.updatedAt ?? null };
    },
  });
  const v = form.values;
  const set = (patch: Partial<IdentityForm>) => form.setValues({ ...v, ...patch });

  return (
    <>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip
          component={RouterLink}
          to="/settings/gst"
          clickable
          variant="outlined"
          color={company.gstin ? 'success' : 'warning'}
          label={
            company.gstin
              ? t('companyPage.gstinChip', { gstin: company.gstin, status: company.gstinVerificationStatus || '—' })
              : t('companyPage.gstinMissing')
          }
        />
      </Stack>
      {form.error ? <Alert severity="error">{settingsErrorText(form.error)}</Alert> : null}
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 640 }}>
        <Stack spacing={2}>
          <Typography variant="h6" component="h2" fontWeight={600}>
            {t('companyPage.identityTitle')}
          </Typography>
          <TextField
            label={t('sweep.shopDisplayName')}
            value={v.name}
            required
            onChange={(e) => set({ name: e.target.value })}
          />
          <TextField label={t('sweep.legalName')} value={v.legalName} onChange={(e) => set({ legalName: e.target.value })} />
          <TextField
            label={t('sweep.shopAddress')}
            multiline
            minRows={2}
            value={v.address}
            onChange={(e) => set({ address: e.target.value })}
          />
          <TextField label={t('sweep.city')} value={v.city} onChange={(e) => set({ city: e.target.value })} />
          <StateSelect value={v.state} onChange={(next: string) => set({ state: next })} />
          <TextField label={t('sweep.pinCode')} value={v.pincode} onChange={(e) => set({ pincode: e.target.value })} />
          <TextField label={t('common.phone')} value={v.phone} onChange={(e) => set({ phone: e.target.value })} />
          <TextField label={t('common.email')} value={v.email} onChange={(e) => set({ email: e.target.value })} />
        </Stack>
      </Paper>
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 640 }}>
        <LogoPanel logoId={company.logo ?? null} />
      </Paper>
      <Paper variant="outlined" sx={{ p: 3, maxWidth: 640 }}>
        <Stack spacing={1.5}>
          <InvoiceBankSummary />
          <Typography variant="body2" color="text.secondary">
            {t('companyPage.movedPrefix')}{' '}
            <Link component={RouterLink} to="/settings/money-in">
              {t('nav.moneyInRules')}
            </Link>
            .
          </Typography>
        </Stack>
      </Paper>
      <SettingsSaveBar form={form} disabled={writesBlocked} />
    </>
  );
}
