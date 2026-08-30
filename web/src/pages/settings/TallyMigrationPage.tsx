import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Stepper from '@mui/material/Stepper';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { getErrorMessage } from '@/api/client';
import { apiClient } from '@/api/client';
import {
  commitTallyImport,
  exportTallyAid,
  previewTallyImport,
  uploadTallyMasters,
} from '@/api/resources';
import { DisclaimerBanner, PageHeader } from '@/components/insights';
import { ErrorState } from '@/components/PageState';
import { t } from '@/i18n';

const STEPS = ['Upload', 'Map', 'Commit', 'Export aid'];

type PreviewParty = {
  name: string;
  phone?: string;
  gstin?: string;
  state?: string;
  opening_outstanding?: string;
  openingOutstanding?: string;
};

type PreviewProduct = {
  name: string;
  sku: string;
  hsn_code?: string;
  hsnCode?: string;
  opening_qty?: string;
  openingQty?: string;
};

type PreviewShape = {
  customers?: PreviewParty[];
  suppliers?: PreviewParty[];
  products?: PreviewProduct[];
  errors?: { row?: number; error?: string }[];
  counts?: Record<string, number>;
};

type MapRow = {
  kind: string;
  name: string;
  sku?: string;
  opening?: string;
  idx: number;
  list: 'customers' | 'suppliers' | 'products';
};

export function TallyMigrationPage() {
  const [step, setStep] = useState(0);
  const [syncRunId, setSyncRunId] = useState<number | null>(null);
  const [preview, setPreview] = useState<PreviewShape | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [committed, setCommitted] = useState(false);

  const mapRows = useMemo(() => {
    if (!preview) return [] as MapRow[];
    const rows: MapRow[] = [];
    (preview.customers ?? []).forEach((r, idx) =>
      rows.push({
        kind: 'customer',
        name: r.name,
        opening: r.opening_outstanding ?? r.openingOutstanding,
        idx,
        list: 'customers',
      }),
    );
    (preview.suppliers ?? []).forEach((r, idx) =>
      rows.push({
        kind: 'supplier',
        name: r.name,
        opening: r.opening_outstanding ?? r.openingOutstanding,
        idx,
        list: 'suppliers',
      }),
    );
    (preview.products ?? []).forEach((r, idx) =>
      rows.push({
        kind: 'product',
        name: r.name,
        sku: r.sku,
        opening: r.opening_qty ?? r.openingQty,
        idx,
        list: 'products',
      }),
    );
    return rows;
  }, [preview]);

  const upload = useMutation({
    mutationFn: (file: File) => uploadTallyMasters(file),
    onSuccess: (data) => {
      setSyncRunId(data.syncRunId);
      setPreview(data.preview as PreviewShape);
      setResult(null);
      setCommitted(false);
      setStep(1);
    },
  });

  const savePreview = async (next: PreviewShape) => {
    if (!syncRunId) throw new Error('No preview');
    const data = await previewTallyImport(syncRunId, next);
    const body = data as { preview?: PreviewShape };
    const saved = body.preview ?? next;
    setPreview(saved);
    return saved;
  };

  const saveMap = useMutation({
    mutationFn: async () => {
      if (!preview) throw new Error('No preview');
      return savePreview(preview);
    },
    onSuccess: () => setStep(1),
  });

  const ignoreErrors = useMutation({
    mutationFn: async () => {
      if (!preview) throw new Error('No preview');
      const cleared: PreviewShape = {
        ...preview,
        errors: [],
        counts: {
          ...(preview.counts ?? {}),
          customers: preview.customers?.length ?? 0,
          suppliers: preview.suppliers?.length ?? 0,
          products: preview.products?.length ?? 0,
          errors: 0,
        },
      };
      return savePreview(cleared);
    },
  });

  const commit = useMutation({
    mutationFn: async () => {
      if (!syncRunId || !preview) throw new Error('No preview');
      // Always persist current map before commit
      await savePreview({ ...preview, errors: preview.errors ?? [] });
      return commitTallyImport(syncRunId);
    },
    onSuccess: (data) => {
      setResult(data);
      setCommitted(true);
      setStep(2);
    },
  });

  const downloadExport = useMutation({
    mutationFn: () => exportTallyAid(),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'bizboard_tally_export_aid.csv';
      a.click();
      URL.revokeObjectURL(url);
      setStep(3);
    },
  });

  const downloadErrors = async () => {
    if (!syncRunId) return;
    const { data, headers } = await apiClient.get(`/integrations/tally/runs/${syncRunId}/errors/`, {
      params: { as: 'csv' },
      responseType: 'blob',
    });
    const ct = String(headers['content-type'] || '');
    if (ct.includes('application/json')) {
      throw new Error('Failed to download error report');
    }
    const url = URL.createObjectURL(data as Blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `tally_errors_${syncRunId}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const counts = (preview?.counts ?? {}) as Record<string, number>;
  const errorCount = preview?.errors?.length ?? counts.errors ?? 0;
  const created = (result?.result as { created?: Record<string, number>; warnings?: string[] })?.created
    ?? (result as { created?: Record<string, number> })?.created;
  const warnings =
    (result?.result as { warnings?: string[] })?.warnings
    ?? (result as { warnings?: string[] })?.warnings
    ?? [];

  const updateMappedName = (list: 'customers' | 'suppliers' | 'products', idx: number, name: string) => {
    setPreview((prev) => {
      if (!prev) return prev;
      const copy = { ...prev, [list]: [...(prev[list] ?? [])] };
      const row = { ...(copy[list] as PreviewParty[] | PreviewProduct[])[idx] };
      (row as PreviewParty).name = name;
      (copy[list] as unknown[])[idx] = row;
      return copy;
    });
  };

  const updateMappedSku = (idx: number, sku: string) => {
    setPreview((prev) => {
      if (!prev?.products) return prev;
      const products = [...prev.products];
      products[idx] = { ...products[idx], sku };
      return { ...prev, products };
    });
  };

  return (
    <Stack spacing={2}>
      <PageHeader title={t('tally.title')} />
      <DisclaimerBanner severity="warning">{t('tally.disclaimer')}</DisclaimerBanner>
      <Stepper activeStep={step} alternativeLabel>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          {t('tally.upload')}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          CSV or Excel (.xlsx). Columns: entity_type (customer|supplier|product), name, phone, gstin,
          state, sku, hsn_code, gst_rate, purchase_price, selling_price, reorder_level, opening_qty,
          opening_outstanding
        </Typography>
        <Button variant="contained" component="label" disabled={committed}>
          Choose CSV / Excel
          <input
            hidden
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate(f);
            }}
          />
        </Button>
        {upload.isError ? <ErrorState message={getErrorMessage(upload.error)} error={upload.error} /> : null}
      </Paper>

      {preview ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle1">{t('tally.map')}</Typography>
          <Typography variant="body2" sx={{ mb: 1 }}>
            Customers: {counts.customers ?? preview.customers?.length ?? 0} · Suppliers:{' '}
            {counts.suppliers ?? preview.suppliers?.length ?? 0} · Products:{' '}
            {counts.products ?? preview.products?.length ?? 0} · Errors: {errorCount}
          </Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Type</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>SKU</TableCell>
                <TableCell>Opening</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {mapRows.map((r) => (
                <TableRow key={`${r.list}-${r.idx}`}>
                  <TableCell>{r.kind}</TableCell>
                  <TableCell>
                    <TextField
                      size="small"
                      value={r.name}
                      onChange={(e) => updateMappedName(r.list, r.idx, e.target.value)}
                      fullWidth
                      disabled={committed}
                      inputProps={{ 'aria-label': `${r.kind} name` }}
                    />
                  </TableCell>
                  <TableCell>
                    {r.list === 'products' ? (
                      <TextField
                        size="small"
                        value={r.sku ?? ''}
                        onChange={(e) => updateMappedSku(r.idx, e.target.value)}
                        disabled={committed}
                        inputProps={{ 'aria-label': 'product sku' }}
                      />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>{r.opening ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {(preview.errors?.length ?? 0) > 0 ? (
            <Stack spacing={0.5} sx={{ mt: 1 }}>
              {preview.errors!.slice(0, 5).map((err, i) => (
                <Typography key={i} variant="caption" color="warning.main">
                  Row {err.row ?? '?'}: {err.error}
                </Typography>
              ))}
            </Stack>
          ) : null}
          <Stack direction="row" spacing={1} sx={{ mt: 2 }} flexWrap="wrap" useFlexGap>
            <Button
              variant="outlined"
              disabled={!syncRunId || saveMap.isPending || committed}
              onClick={() => saveMap.mutate()}
            >
              Save mapping
            </Button>
            {errorCount > 0 ? (
              <>
                <Button variant="outlined" color="warning" onClick={() => void downloadErrors()}>
                  Download error report
                </Button>
                <Button
                  variant="outlined"
                  disabled={ignoreErrors.isPending || committed}
                  onClick={() => ignoreErrors.mutate()}
                >
                  Ignore error rows
                </Button>
              </>
            ) : null}
            <Button
              variant="contained"
              disabled={!syncRunId || commit.isPending || errorCount > 0 || committed}
              onClick={() => commit.mutate()}
            >
              {t('tally.commit')}
            </Button>
          </Stack>
          {saveMap.isError ? <ErrorState message={getErrorMessage(saveMap.error)} error={saveMap.error} /> : null}
          {ignoreErrors.isError ? <ErrorState message={getErrorMessage(ignoreErrors.error)} error={ignoreErrors.error} /> : null}
          {commit.isError ? <ErrorState message={getErrorMessage(commit.error)} error={commit.error} /> : null}
          {created ? (
            <Stack spacing={0.5} sx={{ mt: 2 }}>
              <Typography variant="subtitle2">Commit summary</Typography>
              <Typography variant="body2">
                Customers {created.customers ?? 0} · Suppliers {created.suppliers ?? 0} · Products{' '}
                {created.products ?? 0} · Opening AR {created.opening_ar ?? 0} · Opening AP{' '}
                {created.opening_ap ?? 0} · Stock {created.stock_movements ?? 0}
              </Typography>
              {warnings.map((w) => (
                <Typography key={w} variant="caption" color="warning.main">
                  {w}
                </Typography>
              ))}
            </Stack>
          ) : null}
        </Paper>
      ) : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle1" sx={{ mb: 1 }}>
          {t('tally.export')}
        </Typography>
        <Button
          variant="outlined"
          onClick={() => downloadExport.mutate()}
          disabled={downloadExport.isPending}
        >
          Download sales voucher CSV aid
        </Button>
        {downloadExport.isError ? (
          <ErrorState message={getErrorMessage(downloadExport.error)} error={downloadExport.error} />
        ) : null}
      </Paper>
    </Stack>
  );
}
