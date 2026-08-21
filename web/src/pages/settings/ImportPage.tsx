import { useEffect, useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
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
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import DownloadIcon from '@mui/icons-material/Download';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import { useMutation } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useSearchParams } from 'react-router-dom';
import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import { commitImport, downloadImportErrorsCsv, uploadImport, voidImport, voidImportRows } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { StatusChip } from '@/components/StatusChip';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import type { ImportJob, ImportKind } from '@/types/domain';
import { canImport } from '@/utils/permissions';
import { statusLabelKey } from '@/utils/status';

const steps = [t('import.stepUpload'), t('import.stepPreview'), t('import.stepCommit')];

const KIND_OPTIONS: ImportKind[] = ['PRODUCTS', 'CUSTOMERS', 'SUPPLIERS', 'OPENING_STOCK'];

const REQUIRED_COLUMNS: Record<Exclude<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>, string[]> = {
  PRODUCTS: ['name'],
  CUSTOMERS: ['name'],
  SUPPLIERS: ['name'],
  OPENING_STOCK: ['sku', 'quantity'],
};

const CSV_TEMPLATES: Record<Exclude<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>, string> = {
  PRODUCTS:
    'name,sku,barcode,hsn_code,gst_rate,purchase_price,selling_price,reorder_level,unit,opening_stock\nSoap,SOAP-1,,3401,18,40,55,5,PCS,25\nPlain Bar,BAR-2,,,,,,,\n',
  CUSTOMERS: 'name,phone,email,gstin,state,address\nRavi Stores,9800000001,,,Karnataka,\nWalk-in Customer,,,,,\n',
  SUPPLIERS: 'name,phone,email,gstin,state,address\nMega Suppliers,9800000002,,,Karnataka,\nLocal Vendor,,,,,\n',
  OPENING_STOCK: 'sku,quantity,unit_cost\nSOAP-1,25,40\nBAR-2,10,\n',
};

const PREVIEW_CAP = 50;
const ERROR_CAP = 100;
const COMMIT_HINT_ROWS = 50;

async function stableUploadKey(file: File, kind: string): Promise<string> {
  const subtle = globalThis.crypto?.subtle;
  if (subtle) {
    const digest = await subtle.digest('SHA-256', await file.arrayBuffer());
    const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
    return `import-upload-${kind}-${hex}`;
  }
  return `import-upload-${kind}-${file.name}-${file.size}-${file.lastModified}`;
}

function downloadTemplate(kind: Exclude<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>) {
  const blob = new Blob([CSV_TEMPLATES[kind]], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${kind.toLowerCase()}_template.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function rowSku(row: Record<string, unknown>): string {
  const data = (row.data as Record<string, unknown>) || row;
  return String(data.sku || '').trim();
}

interface NormalizedErrorRow {
  row: number | string;
  errors: string[];
  data?: Record<string, unknown>;
}

function extractErrorRows(job: ImportJob | null): NormalizedErrorRow[] {
  if (!job) return [];
  const list: NormalizedErrorRow[] = [];

  if (Array.isArray(job.errors)) {
    for (let i = 0; i < job.errors.length; i++) {
      const err = job.errors[i];
      if (!err) continue;
      if (typeof err === 'string') {
        list.push({ row: i + 1, errors: [err] });
      } else if (typeof err === 'object') {
        const errObj = err as Record<string, unknown>;
        const rowNum = (errObj.row ?? errObj.rowNumber ?? errObj.row_number ?? i + 1) as number | string;
        const rawErrors = errObj.errors ?? errObj.error ?? errObj.messages ?? errObj.message;
        const errList = Array.isArray(rawErrors)
          ? rawErrors.map((e) => String(e))
          : rawErrors
            ? [String(rawErrors)]
            : ['Validation error'];
        const data = (errObj.data ?? errObj.rowData ?? errObj.row_data) as Record<string, unknown> | undefined;
        list.push({ row: rowNum, errors: errList, data });
      }
    }
  } else if (job.errors && typeof job.errors === 'object') {
    for (const [key, val] of Object.entries(job.errors)) {
      const errList = Array.isArray(val)
        ? val.map((e) => String(e))
        : [String(val || 'Validation error')];
      list.push({ row: key, errors: errList });
    }
  }

  // Fallback: check job.preview for rows with embedded errors
  if (list.length === 0 && Array.isArray(job.preview)) {
    for (let i = 0; i < job.preview.length; i++) {
      const item = job.preview[i] as Record<string, unknown>;
      if (item && Array.isArray(item.errors) && item.errors.length > 0) {
        list.push({
          row: (item.rowNumber ?? item.row ?? i + 1) as number | string,
          errors: item.errors.map(String),
          data: (item.data ?? item) as Record<string, unknown>,
        });
      }
    }
  }

  return list;
}

export function ImportPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnPath = searchParams.get('return');
  const initialKind = useMemo(() => {
    const raw = (searchParams.get('kind') || 'PRODUCTS').toUpperCase();
    return (KIND_OPTIONS.includes(raw as ImportKind) ? raw : 'PRODUCTS') as ImportKind;
  }, [searchParams]);
  const [kind, setKind] = useState<ImportKind>(initialKind);
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [commitKey, setCommitKey] = useState(() => newIdempotencyKey());
  const [uploadKey, setUploadKey] = useState('');
  const [commitElapsed, setCommitElapsed] = useState(0);
  const [voidingSku, setVoidingSku] = useState<string | null>(null);

  useEffect(() => {
    setKind(initialKind);
  }, [initialKind]);

  useEffect(() => {
    let cancelled = false;
    if (!file) {
      setUploadKey('');
      return;
    }
    void stableUploadKey(file, kind).then((key) => {
      if (!cancelled) setUploadKey(key);
    });
    return () => {
      cancelled = true;
    };
  }, [file, kind]);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error('Choose a file');
      const key = uploadKey || (await stableUploadKey(file, kind));
      return uploadImport(file, kind, { idempotencyKey: key });
    },
    onSuccess: (data) => {
      setJob(data);
      setActiveStep(1);
      setError(null);
      setCommitKey(newIdempotencyKey());
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const commitMutation = useMutation({
    mutationFn: () => {
      if (!job) throw new Error('No import job');
      return commitImport(job.id, undefined, { idempotencyKey: `import-commit-${job.id}-${commitKey}` });
    },
    onSuccess: (data) => {
      if ('status' in data && data.status === 'COMMITTED') {
        setJob((prev) => (prev ? { ...prev, ...data, status: 'COMMITTED' } : prev));
      }
      setActiveStep(2);
      setError(null);
      if (returnPath?.startsWith('/') && !returnPath.startsWith('//')) {
        navigate(returnPath, { replace: true });
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  useEffect(() => {
    if (!commitMutation.isPending) {
      setCommitElapsed(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setCommitElapsed(Math.floor((Date.now() - started) / 1000));
    }, 500);
    return () => window.clearInterval(id);
  }, [commitMutation.isPending]);

  const voidMutation = useMutation({
    mutationFn: () => {
      if (!job) throw new Error('No import job');
      return voidImport(job.id);
    },
    onSuccess: (data) => {
      setJob(data);
      setError(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const voidRowMutation = useMutation({
    mutationFn: (sku: string) => {
      if (!job) throw new Error('No import job');
      return voidImportRows(job.id, [sku]);
    },
    onSuccess: (data) => {
      setJob(data);
      setError(null);
      setVoidingSku(null);
    },
    onError: (err) => {
      setVoidingSku(null);
      setError(getErrorMessage(err));
    },
  });

  const errorRows = useMemo(() => extractErrorRows(job), [job]);

  if (!canImport(user)) return <ForbiddenPage />;

  const previewRows = Array.isArray(job?.preview) ? (job!.preview as Record<string, unknown>[]) : [];
  const shownPreview = previewRows.slice(0, PREVIEW_CAP);
  const shownErrors = errorRows.slice(0, ERROR_CAP);
  const needsStockConfirm = kind === 'PRODUCTS' || kind === 'OPENING_STOCK';
  const requiredLabel = REQUIRED_COLUMNS[kind as Exclude<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>].join(', ');
  const columnMappings = job?.columnMappings ?? [];
  const voidedSkus = new Set(
    (job?.voidedRows ?? []).map((row) => (row.sku || '').trim().toLowerCase()).filter(Boolean),
  );
  const previewTruncated = job?.previewTruncated ?? Math.max(0, previewRows.length - PREVIEW_CAP);
  const errorsTruncated = job?.errorsTruncated ?? Math.max(0, errorRows.length - ERROR_CAP);
  const voidBlocked = Boolean(
    error && /already been used|insufficient available stock|Adjust Stock/i.test(error),
  );

  const onCommitClick = () => {
    if (needsStockConfirm) {
      const ok = window.confirm(
        `${t('import.commitConfirmTitle')}\n\n${t('import.commitConfirmBody')}`,
      );
      if (!ok) return;
    }
    commitMutation.mutate();
  };

  const onVoidClick = () => {
    const ok = window.confirm(t('import.voidConfirm'));
    if (!ok) return;
    voidMutation.mutate();
  };

  const onVoidRowClick = (sku: string) => {
    if (!sku) return;
    const ok = window.confirm(t('import.voidRowConfirm', { sku }));
    if (!ok) return;
    setVoidingSku(sku);
    voidRowMutation.mutate(sku);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('import.title')}</Typography>
      <Button
        component={RouterLink}
        to="/purchases/bill-upload"
        variant="text"
        sx={{ alignSelf: 'flex-start' }}
      >
        {t('import.billUploadLink')}
      </Button>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {voidBlocked ? (
        <Alert
          severity="warning"
          action={
            <Button component={RouterLink} to="/inventory/adjustments" color="inherit" size="small">
              {t('import.adjustStockCta')}
            </Button>
          }
        >
          {t('import.voidBlockedHint')}
        </Alert>
      ) : null}
      <Stepper activeStep={activeStep} alternativeLabel>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          <TextField
            select
            label={t('import.entityType')}
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as ImportKind);
              setJob(null);
              setActiveStep(0);
              setFile(null);
            }}
            sx={{ maxWidth: 320 }}
          >
            <MenuItem value="PRODUCTS">Products</MenuItem>
            <MenuItem value="CUSTOMERS">Customers</MenuItem>
            <MenuItem value="SUPPLIERS">Suppliers</MenuItem>
            <MenuItem value="OPENING_STOCK">Opening stock</MenuItem>
          </TextField>

          <Typography variant="body2" color="text.secondary">
            {t('import.csvOnlyHint')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('import.requiredColumnsHint', { columns: requiredLabel })}
          </Typography>

          {kind === 'PRODUCTS' ? (
            <Alert severity="info" icon={<InfoOutlinedIcon fontSize="inherit" />} sx={{ mt: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                {t('import.fieldTipsTitle')}
              </Typography>
              <Stack spacing={0.5}>
                <Typography variant="body2">• {t('import.fieldTipsPrices')}</Typography>
                <Typography variant="body2">• {t('import.fieldTipsGstRate')}</Typography>
                <Typography variant="body2">• {t('import.fieldTipsReorder')}</Typography>
              </Stack>
            </Alert>
          ) : null}

          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Button variant="outlined" component="label">
              {t('import.chooseFile')}
              <input
                hidden
                type="file"
                accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Button>
            <Button
              variant="text"
              onClick={() => downloadTemplate(kind as Exclude<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>)}
            >
              {t('import.downloadTemplate')}
            </Button>
          </Stack>
          {file ? <Typography variant="body2">Selected: {file.name}</Typography> : null}

          <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
            <Button
              variant="contained"
              disabled={!file || uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              {uploadMutation.isPending ? t('import.validating') : t('common.upload')}
            </Button>
            <Button
              variant="contained"
              color="secondary"
              disabled={!job || job.validRows === 0 || commitMutation.isPending || activeStep < 1 || job.status === 'COMMITTED' || job.status === 'VOIDED'}
              onClick={onCommitClick}
            >
              {commitMutation.isPending
                ? t('import.committingElapsed', { seconds: commitElapsed })
                : t('common.commit')}
            </Button>
          </Stack>
          {commitMutation.isPending && (job?.validRows ?? 0) >= COMMIT_HINT_ROWS ? (
            <Typography variant="body2" color="text.secondary">
              {t('import.committingHint')}
            </Typography>
          ) : null}
        </Stack>
      </Paper>

      {job ? (
        <Paper sx={{ p: 2 }}>
          <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap">
            <StatusChip tone="info" labelKey={statusLabelKey(job.status)} />
            <Typography>
              {t('import.validRows')}: <strong>{job.validRows}</strong> / {job.totalRows}
            </Typography>
            {job.errorRows > 0 ? (
              <Typography color="error">
                {t('import.errorRows')}: <strong>{job.errorRows}</strong>
              </Typography>
            ) : null}
            {job.errorRows > 0 ? (
              <Button
                size="small"
                variant="outlined"
                color="error"
                startIcon={<DownloadIcon />}
                onClick={() => {
                  void downloadImportErrorsCsv(job.id, kind);
                }}
              >
                {t('import.downloadErrors')}
              </Button>
            ) : null}
          </Stack>

          {columnMappings.length > 0 ? (
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="subtitle2">{t('import.columnMappedTitle')}</Typography>
              {columnMappings.map((mapping) => (
                <Typography key={`${mapping.source}-${mapping.target}`} variant="body2">
                  {t('import.columnMapped', { source: mapping.source, target: mapping.target })}
                </Typography>
              ))}
            </Alert>
          ) : null}

          {(errorRows.length > 0 || (job.errorRows ?? 0) > 0) ? (
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                mb: 3,
                borderColor: 'error.main',
                bgcolor: 'action.hover',
                borderRadius: 1,
              }}
            >
              <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <ErrorOutlineIcon color="error" />
                    <Typography variant="subtitle1" color="error.main" sx={{ fontWeight: 700 }}>
                      {t('import.validationErrorsTitle', { count: job.errorRows || errorRows.length })}
                    </Typography>
                  </Stack>
                  <Button
                    size="small"
                    variant="contained"
                    color="error"
                    startIcon={<DownloadIcon />}
                    onClick={() => {
                      void downloadImportErrorsCsv(job.id, kind);
                    }}
                  >
                    {t('import.downloadErrors')}
                  </Button>
                </Stack>

                <Alert severity="error">
                  {t('import.validationErrorsHint')}
                </Alert>

                {shownErrors.length > 0 ? (
                  <Table size="small" sx={{ bgcolor: 'background.paper', borderRadius: 1, overflow: 'hidden' }}>
                    <TableHead>
                      <TableRow sx={{ bgcolor: 'action.hover' }}>
                        <TableCell sx={{ width: 90, fontWeight: 700 }}>{t('import.rowNumber')}</TableCell>
                        <TableCell sx={{ fontWeight: 700 }}>{t('import.errorsHeader')}</TableCell>
                        <TableCell sx={{ fontWeight: 700 }}>{t('import.inputDataHeader')}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {shownErrors.map((err, idx) => (
                        <TableRow key={idx} sx={{ '&:hover': { bgcolor: 'action.hover' } }}>
                          <TableCell sx={{ fontWeight: 700, color: 'error.dark' }}>
                            {err.row ?? idx + 1}
                          </TableCell>
                          <TableCell>
                            <Stack spacing={0.5}>
                              {err.errors.map((msg, eIdx) => (
                                <Typography
                                  key={eIdx}
                                  variant="body2"
                                  sx={{ color: 'error.main', fontWeight: 600 }}
                                >
                                  • {msg}
                                </Typography>
                              ))}
                            </Stack>
                          </TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                            {err.data ? (
                              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                                {Object.entries(err.data)
                                  .filter(([_, v]) => v !== undefined && v !== null && v !== '')
                                  .map(([k, v]) => (
                                    <Typography
                                      key={k}
                                      variant="caption"
                                      sx={{ bgcolor: 'action.selected', px: 0.75, py: 0.25, borderRadius: 0.5 }}
                                    >
                                      <strong>{k}:</strong> {String(v)}
                                    </Typography>
                                  ))}
                              </Stack>
                            ) : (
                              '—'
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : null}

                {errorsTruncated > 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('import.errorsMore', { count: errorsTruncated })}
                  </Typography>
                ) : null}
              </Stack>
            </Paper>
          ) : null}

          {shownPreview.length > 0 ? (
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center">
                <CheckCircleOutlineIcon color="success" />
                <Typography variant="subtitle1" color="success.dark" sx={{ fontWeight: 700 }}>
                  {t('import.validPreviewTitle', { count: job.validRows })}
                </Typography>
              </Stack>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: 'action.hover' }}>
                    <TableCell sx={{ width: 60 }}>#</TableCell>
                    <TableCell>Details</TableCell>
                    {job.status === 'COMMITTED' && needsStockConfirm ? (
                      <TableCell sx={{ width: 140 }} />
                    ) : null}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {shownPreview.map((row, idx) => {
                    const rowData = (row.data as Record<string, string>) || (row as Record<string, string>);
                    const sku = rowSku(row);
                    const alreadyVoided = sku ? voidedSkus.has(sku.toLowerCase()) : false;
                    return (
                      <TableRow key={idx}>
                        <TableCell>{idx + 1}</TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                            {Object.entries(rowData).map(([k, v]) =>
                              v ? (
                                <Typography key={k} variant="body2" sx={{ mr: 1 }}>
                                  <strong>{k}:</strong> {String(v)}
                                </Typography>
                              ) : null,
                            )}
                          </Stack>
                        </TableCell>
                        {job.status === 'COMMITTED' && needsStockConfirm ? (
                          <TableCell>
                            {alreadyVoided ? (
                              <Typography variant="body2" color="text.secondary">
                                {t('import.voidedRow')}
                              </Typography>
                            ) : sku ? (
                              <Button
                                size="small"
                                color="warning"
                                disabled={voidRowMutation.isPending}
                                onClick={() => onVoidRowClick(sku)}
                              >
                                {voidingSku === sku ? t('import.voidingRow') : t('import.voidRow')}
                              </Button>
                            ) : null}
                          </TableCell>
                        ) : null}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              {previewTruncated > 0 ? (
                <Typography variant="body2" color="text.secondary">
                  {t('import.previewMore', { count: previewTruncated })}
                </Typography>
              ) : null}
            </Stack>
          ) : null}

          {job.status === 'COMMITTED' ? (
            <Alert severity="success" sx={{ mt: 2 }}>
              {t('import.committed')}
            </Alert>
          ) : null}
          {job.status === 'VOIDED' ? (
            <Alert severity="info" sx={{ mt: 2 }}>
              {t('import.voided')}
            </Alert>
          ) : null}
          {job.status === 'COMMITTED' && (kind === 'PRODUCTS' || kind === 'OPENING_STOCK') ? (
            <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ mt: 1 }}>
              <Button component={RouterLink} to="/inventory/products" variant="outlined">
                {t('import.viewProducts')}
              </Button>
              <Button component={RouterLink} to="/inventory/adjustments" variant="outlined">
                {t('import.adjustStockCta')}
              </Button>
              <Button
                color="warning"
                variant="outlined"
                disabled={voidMutation.isPending}
                onClick={onVoidClick}
              >
                {voidMutation.isPending ? t('import.voiding') : t('import.voidImport')}
              </Button>
            </Stack>
          ) : null}
          {job.status === 'COMMITTED' && kind === 'CUSTOMERS' ? (
            <Button component={RouterLink} to="/sales/customers" variant="outlined" sx={{ mt: 1 }}>
              View Customers
            </Button>
          ) : null}
          {job.status === 'COMMITTED' && kind === 'SUPPLIERS' ? (
            <Button component={RouterLink} to="/purchases/suppliers" variant="outlined" sx={{ mt: 1 }}>
              View Suppliers
            </Button>
          ) : null}
        </Paper>
      ) : null}
    </Stack>
  );
}
