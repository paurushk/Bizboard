import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { downloadGstCaPack, downloadGstReturn, getGstReturn, listCompanyGstins } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import { canExport } from '@/utils/permissions';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

type GstReturnKind = 'gstr1' | 'gstr3b';

function currentPeriod(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  return `${now.getFullYear()}-${month}`;
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

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between" spacing={2}>
      <Typography color="text.secondary">{label}</Typography>
      <Typography fontWeight={600}>{value}</Typography>
    </Stack>
  );
}

function isCompositionUnavailableError(message: string): boolean {
  const m = message.toLowerCase();
  return (
    m.includes('composition') ||
    m.includes('cmp-08') ||
    m.includes('not available')
  );
}

function GstReturnPage({ kind }: { kind: GstReturnKind }) {
  const { user } = useAuth();
  const [period, setPeriod] = useState(currentPeriod());
  const [format, setFormat] = useState<'json' | 'xlsx'>('xlsx');
  const [companyGstin, setCompanyGstin] = useState<string>('');
  const title = kind === 'gstr1' ? t('nav.gstr1') : t('nav.gstr3b');
  const gstins = useQuery({ queryKey: ['company-gstins'], queryFn: listCompanyGstins });

  const query = useQuery({
    queryKey: ['gst-return', kind, period, companyGstin],
    queryFn: () => getGstReturn(kind, { period, companyGstin: companyGstin || undefined }),
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
      downloadBlobUrl(result.url, `${kind}-${period}.${ext}`);
    },
  });

  const caPackMutation = useMutation({
    mutationFn: () =>
      downloadGstCaPack({ period, companyGstin: companyGstin || undefined }),
    onSuccess: (result) => downloadBlobUrl(result.url, `gst-ca-pack-${period}.zip`),
  });

  const issues = (query.data?.issues as Array<{ code?: string; message?: string; number?: string }> | undefined) ?? [];
  const queryErrorMessage = query.isError ? getErrorMessage(query.error) : '';
  const compositionBlocked = query.isError && isCompositionUnavailableError(queryErrorMessage);

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
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
        <Typography variant="h4">{title}</Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <TextField
            type="month"
            size="small"
            label={t('reports.period')}
            InputLabelProps={{ shrink: true }}
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          />
          <TextField
            select
            size="small"
            label="Company GSTIN"
            value={companyGstin}
            onChange={(e) => setCompanyGstin(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">All / primary</MenuItem>
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
                onChange={(e) => setFormat(e.target.value as 'json' | 'xlsx')}
                sx={{ minWidth: 120 }}
              >
                <MenuItem value="json">JSON</MenuItem>
                <MenuItem value="xlsx">XLSX</MenuItem>
              </TextField>
              <Button
                variant="outlined"
                disabled={exportMutation.isPending}
                onClick={() => exportMutation.mutate()}
              >
                {t('common.export')}
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
      </Stack>

      <Alert severity="info">{t('reports.gstOfflineDisclaimer')}</Alert>
      {kind === 'gstr1' ? <Alert severity="warning">{t('reports.supecomWarning')}</Alert> : null}
      {kind === 'gstr3b' && (query.data?.itc as { provisional?: boolean; disclaimer?: string } | undefined)?.provisional ? (
        <Alert severity="warning">
          {String(
            (query.data!.itc as { disclaimer?: string }).disclaimer
              ?? t('reports.itcProvisionalBanner'),
          )}
        </Alert>
      ) : null}
      {issues.length > 0 ? (
        <Alert severity="warning">
          {t('reports.issuesStrip')}: {issues.length}
          <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
            {issues.slice(0, 8).map((issue, idx) => (
              <li key={idx}>
                {issue.number ? `${issue.number}: ` : ''}
                {issue.message ?? issue.code}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}

      {exportMutation.isError ? (
        <HelpErrorAlert error={exportMutation.error} />
      ) : null}
      {compositionBlocked ? (
        <Alert severity="warning">
          Composition dealers cannot use GSTR-1 / GSTR-3B return aids in BizBoard. Use the CMP-08 and
          GSTR-4 worksheet aids, then file on the GST portal or with your CA.
        </Alert>
      ) : null}
      {query.isLoading ? <LoadingState /> : null}
      {query.isError && !compositionBlocked ? (
        <ErrorState message={queryErrorMessage} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}

      {query.data && outward ? (
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            {kind === 'gstr3b' ? (
              (() => {
                const outwardRec = outward as Record<string, string | number>;
                const itcData = ((query.data?.itc ?? query.data?.inwardSupplies ?? {}) as Record<string, string | number>);
                const totalTaxLiability = toNumber(outwardRec.cgst ?? 0) + toNumber(outwardRec.sgst ?? 0) + toNumber(outwardRec.igst ?? 0);
                // R4-004: prefer the backend's recommended claimable ITC
                // (min(books, GSTR-2B matched) per head) when it is provided —
                // that is the amount safe to actually claim.
                const rec = (itcData.recommendedClaimable ?? itcData.recommended_claimable) as unknown as
                  | Record<string, string | number>
                  | undefined;
                const recTotal = rec
                  ? toNumber(rec.cgst ?? 0) + toNumber(rec.sgst ?? 0) + toNumber(rec.igst ?? 0)
                  : null;
                const totalItc = recTotal != null
                  ? recTotal
                  : toNumber(itcData.cgst ?? itcData.available_cgst ?? itcData.availableCgst ?? 0) +
                    toNumber(itcData.sgst ?? itcData.available_sgst ?? itcData.availableSgst ?? 0) +
                    toNumber(itcData.igst ?? itcData.available_igst ?? itcData.availableIgst ?? 0);
                const netGstPayable = Math.max(0, totalTaxLiability - totalItc);

                return (
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 2,
                      bgcolor: 'primary.50',
                      borderColor: 'primary.main',
                      borderRadius: 1,
                    }}
                  >
                    <Typography variant="subtitle1" fontWeight={700} color="primary.main">
                      {t('billing.netGstPayable')}
                    </Typography>
                    <Typography variant="h4" fontWeight={700} sx={{ my: 1, color: netGstPayable > 0 ? 'error.main' : 'success.main' }}>
                      {formatMoney(netGstPayable)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Tax collected on Sales ({formatMoney(totalTaxLiability)}) − ITC from Purchases ({formatMoney(totalItc)})
                    </Typography>
                    {rec ? (
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                        ITC basis: {String(rec.basis ?? 'books')}
                        {String(rec.basis ?? '') === 'min(books, gstr2b_matched)'
                          ? ' — the lower of your books and GSTR-2B matched'
                          : ' — provisional until GSTR-2B match'}
                      </Typography>
                    ) : null}
                  </Paper>
                );
              })()
            ) : null}

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
    </Stack>
  );
}

export function Gstr1ReportPage() {
  return <GstReturnPage kind="gstr1" />;
}

export function Gstr3bReportPage() {
  return <GstReturnPage kind="gstr3b" />;
}

function GstStubPage({ kind }: { kind: 'gstr4' | 'cmp08' | 'gstr6' | 'gstr7' | 'gstr8' }) {
  const [period, setPeriod] = useState(currentPeriod());
  const title =
    kind === 'gstr4'
      ? t('nav.gstr4')
      : kind === 'cmp08'
        ? t('nav.cmp08')
        : kind === 'gstr6'
          ? t('nav.gstr6')
          : kind === 'gstr7'
            ? t('nav.gstr7')
            : t('nav.gstr8');
  // `getGstReturn` only serves gstr6/7/8 here (gstr4 / cmp08 render from their
  // own components); `enabled` guarantees the queryFn never runs for those.
  const isServerReturn = kind === 'gstr6' || kind === 'gstr7' || kind === 'gstr8';
  const query = useQuery({
    queryKey: ['gst-return', kind, period],
    queryFn: () =>
      getGstReturn(kind as 'gstr6' | 'gstr7' | 'gstr8', { period }),
    enabled: isServerReturn,
  });
  return (
    <Stack spacing={2}>
      <Typography variant="h4">{title}</Typography>
      <TextField
        type="month"
        size="small"
        label={t('reports.period')}
        InputLabelProps={{ shrink: true }}
        value={period}
        onChange={(e) => setPeriod(e.target.value)}
        sx={{ maxWidth: 220 }}
      />
      <Alert severity="warning">
        <Typography fontWeight={600}>{t('gstHonesty.stubTitle')}</Typography>
        <Typography variant="body2">{t('gstHonesty.stubBody')}</Typography>
      </Alert>
      {query.isLoading ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
      ) : null}
      {query.data ? (
        <details>
          <summary>{t('gstHonesty.rawPayload')}</summary>
          <Paper sx={{ p: 2, overflow: 'auto', mt: 1 }}>
            <Typography variant="body2" component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap' }}>
              {JSON.stringify(query.data, null, 2)}
            </Typography>
          </Paper>
        </details>
      ) : null}
    </Stack>
  );
}

export function Gstr4ReportPage() {
  return <GstStubPage kind="gstr4" />;
}

export function Cmp08ReportPage() {
  return <GstStubPage kind="cmp08" />;
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
