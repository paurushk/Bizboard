import { useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import CircularProgress from '@mui/material/CircularProgress';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  commitImport,
  getImportJob,
  listSuppliers,
  retryImportExtract,
  updateImportPreview,
  uploadImport,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { StatusChip } from '@/components/StatusChip';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { t } from '@/i18n';
import type {
  ImportJob,
  PurchaseBillCommitResult,
  PurchaseBillLinePreview,
  PurchaseBillPreview,
} from '@/types/domain';
import { canImport } from '@/utils/permissions';
import { statusLabelKey } from '@/utils/status';

function isBillPreview(preview: ImportJob['preview']): preview is PurchaseBillPreview {
  return !!preview && !Array.isArray(preview) && Array.isArray((preview as PurchaseBillPreview).lines);
}

function normalizeLines(preview: PurchaseBillPreview | null): PurchaseBillLinePreview[] {
  if (!preview?.lines) return [];
  return preview.lines.map((line) => ({
    name: line.name ?? '',
    sku: line.sku ?? '',
    hsnCode: line.hsnCode ?? (line as { hsn_code?: string }).hsn_code ?? '',
    quantity: String(line.quantity ?? '1'),
    unitPrice: String(
      line.unitPrice ?? (line as { unit_price?: string }).unit_price ?? '0',
    ),
    gstRate: String(line.gstRate ?? (line as { gst_rate?: string }).gst_rate ?? '18'),
    mrp: String(line.mrp ?? '0'),
    include: line.include !== false,
  }));
}

export function PurchaseBillUploadPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const suppliersQuery = useQuery({ queryKey: ['suppliers'], queryFn: () => listSuppliers() });

  const [file, setFile] = useState<File | null>(null);
  const [supplierId, setSupplierId] = useState<number | ''>('');
  const [jobId, setJobId] = useState<number | null>(null);
  const [lines, setLines] = useState<PurchaseBillLinePreview[]>([]);
  const [billNumber, setBillNumber] = useState('');
  const [billDate, setBillDate] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const jobQuery = useQuery({
    queryKey: ['import-job', jobId],
    queryFn: () => getImportJob(jobId!),
    enabled: jobId != null,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === 'UPLOADED' || status === 'EXTRACTING') return 1500;
      return false;
    },
  });

  const job = jobQuery.data;

  useEffect(() => {
    if (!job || !isBillPreview(job.preview)) return;
    if (job.status !== 'PREVIEWED') return;
    setLines(normalizeLines(job.preview));
    setBillNumber(job.preview.billNumber ?? '');
    setBillDate(job.preview.billDate ?? '');
    if (job.supplier) setSupplierId(job.supplier);
  }, [job]);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose a file');
      return uploadImport(file, 'PURCHASE_BILL', {
        supplierId: supplierId === '' ? undefined : supplierId,
      });
    },
    onSuccess: (data) => {
      setJobId(data.id);
      setError(null);
      setSuccessMsg(null);
      if (data.status === 'FAILED') {
        setError(data.failureReason || 'Extraction failed');
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) throw new Error('No job');
      const payloadLines = lines.map((line) => ({
        name: line.name,
        sku: line.sku ?? '',
        hsnCode: line.hsnCode ?? '',
        quantity: line.quantity,
        unitPrice: line.unitPrice,
        gstRate: line.gstRate,
        mrp: line.mrp ?? '0',
        include: line.include !== false,
      }));
      await updateImportPreview(jobId, {
        supplierId: supplierId === '' ? null : supplierId,
        billNumber,
        billDate,
        lines: payloadLines,
      });
      return commitImport(jobId, {
        supplierId: supplierId === '' ? undefined : supplierId,
        billNumber,
        billDate,
        lines: payloadLines,
      });
    },
    onSuccess: (result) => {
      const purchaseId =
        'purchaseInvoiceId' in result
          ? (result as PurchaseBillCommitResult).purchaseInvoiceId
          : undefined;
      setSuccessMsg(t('billUpload.success'));
      setError(null);
      if (purchaseId) {
        void navigate('/purchases/history', {
          state: { message: `Draft purchase #${purchaseId} created from bill upload.` },
        });
      }
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const extracting = useMemo(
    () =>
      uploadMutation.isPending ||
      job?.status === 'UPLOADED' ||
      job?.status === 'EXTRACTING' ||
      (jobId != null && jobQuery.isLoading),
    [uploadMutation.isPending, job?.status, jobId, jobQuery.isLoading],
  );

  const includedCount = lines.filter((l) => l.include !== false).length;

  if (!canImport(user)) return <ForbiddenPage />;

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('billUpload.title')}</Typography>
      <Typography color="text.secondary">{t('billUpload.subtitle')}</Typography>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {successMsg ? <Alert severity="success">{successMsg}</Alert> : null}
      {job?.status === 'FAILED' && job.failureReason ? (
        <Alert
          severity="error"
          action={
            <Stack direction="row" spacing={1}>
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  if (jobId != null) {
                    void retryImportExtract(jobId).then(() => {
                      void jobQuery.refetch();
                    });
                  }
                }}
              >
                {t('billUpload.retryExtract')}
              </Button>
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  setJobId(null);
                  setFile(null);
                  setLines([]);
                  setError(null);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
              >
                {t('billUpload.reset')}
              </Button>
            </Stack>
          }
        >
          {job.failureReason}
        </Alert>
      ) : null}

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          <TextField
            select
            label={t('billUpload.supplierHint')}
            value={supplierId === '' ? '' : String(supplierId)}
            onChange={(e) =>
              setSupplierId(e.target.value === '' ? '' : Number(e.target.value))
            }
            sx={{ maxWidth: 420 }}
          >
            <MenuItem value="">— Auto from bill / create —</MenuItem>
            {(suppliersQuery.data ?? []).map((s) => (
              <MenuItem key={s.id} value={String(s.id)}>
                {s.name}
              </MenuItem>
            ))}
          </TextField>

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/*"
            style={{ display: 'none' }}
            onChange={(e) => {
              const next = e.target.files?.[0] ?? null;
              setFile(next);
              setError(null);
            }}
          />
          <Button
            variant="outlined"
            sx={{ alignSelf: 'flex-start' }}
            onClick={() => fileInputRef.current?.click()}
          >
            {t('billUpload.chooseFile')}
          </Button>
          {file ? <Typography variant="body2">Selected: {file.name}</Typography> : null}

          <Button
            variant="contained"
            disabled={!file || extracting}
            onClick={() => uploadMutation.mutate()}
          >
            {t('common.upload')}
          </Button>
        </Stack>
      </Paper>

      {extracting ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={22} />
          <Typography>{t('billUpload.extracting')}</Typography>
          {job ? <StatusChip tone="info" labelKey={statusLabelKey(job.status)} /> : null}
        </Stack>
      ) : null}

      {job?.status === 'PREVIEWED' ? (
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Stack direction="row" spacing={2} flexWrap="wrap">
              <TextField
                label={t('billUpload.billNumber')}
                value={billNumber}
                onChange={(e) => setBillNumber(e.target.value)}
                sx={{ minWidth: 200 }}
              />
              <TextField
                label={t('billUpload.billDate')}
                type="date"
                InputLabelProps={{ shrink: true }}
                value={billDate}
                onChange={(e) => setBillDate(e.target.value)}
                sx={{ minWidth: 200 }}
              />
            </Stack>

            {lines.length === 0 ? (
              <Alert severity="warning">{t('billUpload.noLines')}</Alert>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('billUpload.include')}</TableCell>
                    <TableCell>{t('common.name')}</TableCell>
                    <TableCell>{t('common.sku')}</TableCell>
                    <TableCell>HSN</TableCell>
                    <TableCell align="right">{t('billing.qty')}</TableCell>
                    <TableCell align="right">{t('billing.price')}</TableCell>
                    <TableCell align="right">GST %</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {lines.map((line, idx) => (
                    <TableRow key={idx}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={line.include !== false}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, include: e.target.checked } : l,
                              ),
                            )
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          size="small"
                          value={line.name}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, name: e.target.value } : l,
                              ),
                            )
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          size="small"
                          value={line.sku ?? ''}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, sku: e.target.value } : l,
                              ),
                            )
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          size="small"
                          value={line.hsnCode ?? ''}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, hsnCode: e.target.value } : l,
                              ),
                            )
                          }
                        />
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={line.quantity}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, quantity: e.target.value } : l,
                              ),
                            )
                          }
                          sx={{ width: 90 }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={line.unitPrice}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, unitPrice: e.target.value } : l,
                              ),
                            )
                          }
                          sx={{ width: 110 }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          type="number"
                          value={line.gstRate}
                          onChange={(e) =>
                            setLines((prev) =>
                              prev.map((l, i) =>
                                i === idx ? { ...l, gstRate: e.target.value } : l,
                              ),
                            )
                          }
                          sx={{ width: 90 }}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}

            <Button
              variant="contained"
              color="secondary"
              disabled={includedCount === 0 || commitMutation.isPending}
              onClick={() => commitMutation.mutate()}
            >
              {t('billUpload.commitDraft')}
            </Button>
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
