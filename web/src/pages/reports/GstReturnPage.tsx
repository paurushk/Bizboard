import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  downloadGstCaPack,
  downloadGstReturn,
  getCmp08,
  getCompany,
  getGstReturn,
  getGstr4,
  listCompanyGstins,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { GstHonestyHeader } from '@/components/GstHonestyHeader';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { AdvanceGstAlert } from '@/pages/reports/AdvanceGstAlert';
import { canExport } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { GstIssuesList, type GstIssue } from '@/pages/reports/GstIssuesList';
import { Gstr1Sections } from '@/pages/reports/Gstr1Sections';
import { GstSnapshotList } from '@/pages/reports/GstSnapshotList';
import { Gstr3bPanel } from '@/pages/reports/Gstr3bPanel';
import { summarizeGstr3b } from '@/pages/reports/gstr3bSummary';
import { PageShell } from '@/pages/phase/phaseShared';

type GstReturnKind = 'gstr1' | 'gstr3b';

function currentPeriod(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${now.getFullYear()}-${month}`;
}

function defaultFy(): string {
  const now = new Date();
  const year = now.getMonth() + 1 >= 4 ? now.getFullYear() : now.getFullYear() - 1;
  const end = String((year + 1) % 100).padStart(2, '0');
  return `${year}-${end}`;
}

function downloadBlobUrl(url: string, filename: string) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function RegisterTieAlert({ data }: { data: Record<string, unknown> }) {
  const tie = (data.registerTie ?? data.register_tie) as Record<string, unknown> | undefined;
  if (!tie) return null;
  // Green only on an explicit true. A missing key must not read as "ties".
  const salesTies = tie.sales === true;
  const delta = String(tie.salesDelta ?? tie.sales_delta ?? '0.00');
  const hasPurchase = tie.purchase != null;
  const purchaseTies = tie.purchase === true;
  const purchaseDelta = String(tie.purchaseDelta ?? tie.purchase_delta ?? '0.00');
  const severity = salesTies && (!hasPurchase || purchaseTies) ? 'success' : 'warning';
  return (
    <Alert severity={severity}>
      <div>{salesTies ? t('gstHonesty.registerTies') : t('gstHonesty.registerMismatch', { delta })}</div>
      {hasPurchase ? (
        <div>
          {purchaseTies
            ? t('gstHonesty.registerPurchaseTies')
            : t('gstHonesty.registerPurchaseMismatch', { delta: purchaseDelta })}
        </div>
      ) : null}
    </Alert>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary">{label}</Typography>
      <Typography fontWeight={600}>{value}</Typography>
    </Stack>
  );
}

function CompositionAidsAlert() {
  return (
    <Alert
      severity="warning"
      action={
        <Stack direction="row" spacing={1}>
          <Button color="inherit" size="small" component={RouterLink} to="/reports/cmp08">
            {t('gstHonesty.openCmp08')}
          </Button>
          <Button color="inherit" size="small" component={RouterLink} to="/reports/gstr4">
            {t('gstHonesty.openGstr4')}
          </Button>
        </Stack>
      }
    >
      {t('gstHonesty.compositionUseAids')}
    </Alert>
  );
}

function CompositionOnlyAlert() {
  return (
    <Alert
      severity="info"
      action={
        <Stack direction="row" spacing={1}>
          <Button color="inherit" size="small" component={RouterLink} to="/reports/gstr1">
            {t('nav.gstr1')}
          </Button>
          <Button color="inherit" size="small" component={RouterLink} to="/reports/gstr3b">
            {t('nav.gstr3b')}
          </Button>
        </Stack>
      }
    >
      {t('gstHonesty.compositionOnly')}
    </Alert>
  );
}

function GstReturnPage({ kind }: { kind: GstReturnKind }) {
  const { user } = useAuth();
  const [period, setPeriod] = useState(currentPeriod());
  const [format, setFormat] = useState<'json' | 'xlsx' | 'gstn-json'>('xlsx');
  const [companyGstin, setCompanyGstin] = useState<string>('');
  const title = kind === 'gstr1' ? t('nav.gstr1') : t('nav.gstr3b');
  // BB-100 F7: the branch-GSTIN list is owner-only (B6-011); others would only get a 403.
  const gstins = useQuery({
    queryKey: ['company-gstins'],
    queryFn: listCompanyGstins,
    enabled: user?.role === 'OWNER',
  });
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const registrationType =
    companyQuery.data?.registrationType ?? user?.company?.registrationType;
  const isComposition = registrationType === 'COMPOSITION';
  const registrationReady =
    companyQuery.isSuccess || companyQuery.isError || Boolean(user?.company);

  const query = useQuery({
    queryKey: ['gst-return', kind, period, companyGstin],
    queryFn: () => getGstReturn(kind, { period, companyGstin: companyGstin || undefined }),
    enabled: registrationReady && !isComposition,
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      downloadGstReturn(kind, {
        period,
        format,
        companyGstin: companyGstin || undefined,
      }),
    onSuccess: (result) => {
      const ext = format === 'xlsx' ? 'xlsx' : 'json';
      downloadBlobUrl(result.url, `${kind}-${period}${format === 'gstn-json' ? '-gstn' : ''}.${ext}`);
    },
  });

  const queryClient = useQueryClient();
  const snapshotMutation = useMutation({
    mutationFn: () => getGstReturn(kind, { period, persist: true, companyGstin: companyGstin || undefined }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['gst-snapshots', kind] }),
  });

  const caPackMutation = useMutation({
    mutationFn: () =>
      downloadGstCaPack({ period, companyGstin: companyGstin || undefined }),
    onSuccess: (result) => downloadBlobUrl(result.url, `gst-ca-pack-${period}.zip`),
    onError: () => undefined, // surfaced by the isError alert below (F3-031)
  });

  const issues = (query.data?.issues as GstIssue[] | undefined) ?? [];
  const queryErrorMessage = query.isError ? getErrorMessage(query.error) : '';

  const outward = useMemo(() => {
    if (!query.data) return null;
    if (kind === 'gstr1') {
      return query.data.totals as Record<string, string | Record<string, string>> | undefined;
    }
    return (query.data.outwardSupplies ?? query.data.outward_supplies) as
      | Record<string, string>
      | undefined;
  }, [query.data, kind]);

  return (
    <PageShell title={title} actions={
<Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <TextField
            type="month"
            size="small"
            label={t('reports.period')}
            InputLabelProps={{ shrink: true }}
            value={period}
            onChange={(e) => { if (e.target.value) setPeriod(e.target.value); }}
          />
          <TextField
            select
            size="small"
            label={t('sweep.companyGstin')}
            value={companyGstin}
            onChange={(e) => setCompanyGstin(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">{t('sweep2.allPrimary')}</MenuItem>
            {(gstins.data ?? []).map((row) => (
              <MenuItem key={row.id} value={String(row.id)}>
                {row.gstin}
              </MenuItem>
            ))}
          </TextField>
          {canExport(user) ? (
            <>
              <TextField
                select
                size="small"
                label={t('reports.format')}
                value={format}
                onChange={(e) => setFormat(e.target.value as 'json' | 'xlsx' | 'gstn-json')}
                helperText={format === 'gstn-json' ? t('gstr3b.gstnJsonHelp') : undefined}
                sx={{ minWidth: 120 }}
              >
                <MenuItem value="json">JSON</MenuItem>
                <MenuItem value="xlsx">XLSX</MenuItem>
                <MenuItem value="gstn-json">{t('gstr3b.gstnJson')}</MenuItem>
              </TextField>
              <Button
                variant="outlined"
                disabled={exportMutation.isPending || isComposition}
                onClick={() => exportMutation.mutate()}
              >
                {t('common.export')}
              </Button>
              <Button
                variant="outlined"
                disabled={snapshotMutation.isPending || isComposition}
                onClick={() => snapshotMutation.mutate()}
              >
                {t('gstr3b.saveSnapshot')}
              </Button>
              <Button
                variant="contained"
                disabled={caPackMutation.isPending}
                onClick={() => caPackMutation.mutate()}
              >
                {t('reports.caPack')}
              </Button>
            </>
          ) : null}
        </Stack>
}>

      <GstHonestyHeader />
      {query.data ? <RegisterTieAlert data={query.data as Record<string, unknown>} /> : null}
      {query.data ? <AdvanceGstAlert data={query.data as Record<string, unknown>} /> : null}
      {kind === 'gstr1' ? <Alert severity="warning">{t('reports.supecomWarning')}</Alert> : null}
      <GstIssuesList issues={issues as GstIssue[]} />

      {snapshotMutation.isSuccess ? <Alert severity="success">{t('gstr3b.snapshotSaved', { period })}</Alert> : null}
      {snapshotMutation.isError ? <HelpErrorAlert error={snapshotMutation.error} /> : null}
      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {caPackMutation.isError ? (
        <HelpErrorAlert error={caPackMutation.error} />
      ) : null}
      {isComposition ? <CompositionAidsAlert /> : null}
      {(!registrationReady && companyQuery.isLoading) || (query.isLoading && !isComposition) ? (
        <LoadingState />
      ) : null}
      {query.isError && !isComposition ? (
        <ErrorState message={queryErrorMessage} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}

      {query.data && outward && !isComposition ? (
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            {kind === 'gstr3b' ? <Gstr3bPanel summary={summarizeGstr3b(query.data as Record<string, unknown>)} /> : null}

            <Typography variant="h6">{t('reports.summary')}</Typography>
            {kind === 'gstr1' ? (
              <>
                <SummaryRow
                  label={t('reports.b2bInvoices')}
                  value={String(Array.isArray(query.data.b2b) ? query.data.b2b.length : 0)}
                />
                <SummaryRow
                  label={t('reports.b2clInvoices')}
                  value={String(Array.isArray(query.data.b2cl) ? query.data.b2cl.length : 0)}
                />
                <SummaryRow
                  label={t('reports.b2csBuckets')}
                  value={String(Array.isArray(query.data.b2cs) ? query.data.b2cs.length : 0)}
                />
                <SummaryRow
                  label={t('reports.creditDebitNotes')}
                  value={String(Array.isArray(query.data.cdnr) ? query.data.cdnr.length : 0)}
                />
                <SummaryRow
                  label={t('reports.outwardTaxable')}
                  value={formatMoney(String((outward as Record<string, string>).outward_taxable ?? (outward as Record<string, string>).outwardTaxable ?? '0'))}
                />
              </>
            ) : (
              <>
                <SummaryRow
                  label={t('reports.outwardTaxable')}
                  value={formatMoney(String(outward.taxableValue ?? outward.taxable_value ?? '0'))}
                />
                <SummaryRow
                  label="IGST"
                  value={formatMoney(String(outward.igst ?? '0'))}
                />
                <SummaryRow
                  label="CGST"
                  value={formatMoney(String(outward.cgst ?? '0'))}
                />
                <SummaryRow
                  label="SGST"
                  value={formatMoney(String(outward.sgst ?? '0'))}
                />
              </>
            )}
          </Stack>
        </Paper>
      ) : null}
      {!isComposition ? <GstSnapshotList kind={kind} /> : null}
      {kind === 'gstr1' && query.data && !isComposition && !query.isError ? (
        <Gstr1Sections data={query.data as Record<string, unknown>} />
      ) : null}
    </PageShell>
  );
}

export function Gstr1ReportPage() {
  return <GstReturnPage kind="gstr1" />;
}

export function Gstr3bReportPage() {
  return <GstReturnPage kind="gstr3b" />;
}

function GstStubPage({ kind }: { kind: 'gstr6' | 'gstr7' | 'gstr8' }) {
  const title =
    kind === 'gstr6' ? t('nav.gstr6') : kind === 'gstr7' ? t('nav.gstr7') : t('nav.gstr8');
  return (
    <PageShell title={title}>
    <Stack spacing={2} alignItems="center" sx={{ textAlign: 'center', py: 4, maxWidth: 480, mx: 'auto' }}>
      <GstHonestyHeader />
      <Alert severity="warning" sx={{ width: '100%', textAlign: 'left' }}>
        <Typography fontWeight={600}>{t('gstHonesty.stubTitle')}</Typography>
        <Typography variant="body2">{t('gstHonesty.stubBody')}</Typography>
      </Alert>
      <Button component={RouterLink} to="/reports/gstr1" variant="contained">{t('gstHonesty.openGstr1')}</Button>
    </Stack>
    </PageShell>
  );
}

function Cmp08WorksheetPage() {
  const [period, setPeriod] = useState(currentPeriod());
  const { user } = useAuth();
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const isComposition =
    (companyQuery.data?.registrationType ?? user?.company?.registrationType) === 'COMPOSITION';
  const query = useQuery({
    queryKey: ['cmp08', period],
    queryFn: () => getCmp08({ period }),
    enabled: isComposition,
  });

  return (
    <PageShell title={t('nav.cmp08')} actions={
<TextField
          type="month"
          size="small"
          label={t('reports.period')}
          InputLabelProps={{ shrink: true }}
          value={period}
          onChange={(e) => { if (e.target.value) setPeriod(e.target.value); }}
          disabled={!isComposition}
        />
}>
      <GstHonestyHeader />
      {companyQuery.isLoading ? <LoadingState /> : null}
      {companyQuery.isSuccess && !isComposition ? <CompositionOnlyAlert /> : null}
      {isComposition && query.isLoading ? <LoadingState /> : null}
      {isComposition && query.isError ? (
        <ErrorState
          message={getErrorMessage(query.error)}
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {isComposition && query.data ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            {query.data.disclaimer ? (
              <Alert severity="info">{String(query.data.disclaimer)}</Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {t('gstHonesty.booksAidNotChallan')}
            </Typography>
            <SummaryRow
              label={t('gstHonesty.cmp08Table1')}
              value={formatMoney(String(query.data.table_1_outward_taxable ?? query.data.outward_taxable ?? '0'))}
            />
            <SummaryRow
              label={t('gstHonesty.cmp08Table2Taxable')}
              value={formatMoney(String(query.data.table_2_inward_rcm_taxable ?? '0'))}
            />
            <SummaryRow
              label={t('gstHonesty.cmp08Table2Tax')}
              value={formatMoney(String(query.data.table_2_inward_rcm_tax ?? '0'))}
            />
            <SummaryRow
              label={t('gstHonesty.cmp08Table3')}
              value={formatMoney(String(query.data.table_3_tax_payable ?? '0'))}
            />
            <SummaryRow
              label={t('gstHonesty.compositionRate')}
              value={String(query.data.composition_rate ?? '')}
            />
          </Stack>
        </Paper>
      ) : null}
    </PageShell>
  );
}

function Gstr4WorksheetPage() {
  const [fy, setFy] = useState(defaultFy());
  const { user } = useAuth();
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const isComposition =
    (companyQuery.data?.registrationType ?? user?.company?.registrationType) === 'COMPOSITION';
  const query = useQuery({
    queryKey: ['gstr4', fy],
    queryFn: () => getGstr4({ fy }),
    enabled: isComposition,
  });
  const tables = (query.data?.tables ?? {}) as Record<string, { note?: string } | string>;

  return (
    <PageShell title={t('nav.gstr4')} actions={
<TextField
          size="small"
          label={t('reports.fy')}
          value={fy}
          onChange={(e) => setFy(e.target.value)}
          helperText={t('sweep.fyExample')}
          disabled={!isComposition}
        />
}>
      <GstHonestyHeader />
      {companyQuery.isLoading ? <LoadingState /> : null}
      {companyQuery.isSuccess && !isComposition ? <CompositionOnlyAlert /> : null}
      {isComposition && query.isLoading ? <LoadingState /> : null}
      {isComposition && query.isError ? (
        <ErrorState
          message={getErrorMessage(query.error)}
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : null}
      {isComposition && query.data ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            {query.data.disclaimer ? (
              <Alert severity="info">{String(query.data.disclaimer)}</Alert>
            ) : null}
            {query.data.supported === false ? (
              <Alert severity="warning">
                <Typography fontWeight={600}>{t('gstHonesty.stubTitle')}</Typography>
                <Typography variant="body2">{t('gstHonesty.stubBody')}</Typography>
              </Alert>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {t('gstHonesty.booksAidNotChallan')}
            </Typography>
            {Object.entries(tables).map(([key, value]) => {
              const note = typeof value === 'string' ? value : value?.note;
              if (!note) return null;
              return (
                <Typography key={key} variant="body2">
                  {key}: {note}
                </Typography>
              );
            })}
          </Stack>
        </Paper>
      ) : null}
    </PageShell>
  );
}

export function Gstr4ReportPage() {
  return <Gstr4WorksheetPage />;
}

export function Cmp08ReportPage() {
  return <Cmp08WorksheetPage />;
}

export function Gstr6ReportPage() {
  return <GstStubPage kind="gstr6" />;
}

export function Gstr7ReportPage() {
  return <GstStubPage kind="gstr7" />;
}

export function Gstr8ReportPage() {
  return <GstStubPage kind="gstr8" />;
}
