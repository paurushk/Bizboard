import { useEffect, useMemo, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import {
  answerImportClarifications,
  commitImport,
  getImportJob,
  listCustomers,
  listSuppliers,
  retryImportExtract,
  updateImportPreview,
  uploadImport,
} from '@/api/resources';
import { StatusChip } from '@/components/StatusChip';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { t } from '@/i18n';
import type {
  ImportJob,
  ImportKind,
  PurchaseBillCommitResult,
  PurchaseBillLinePreview,
  PurchaseBillPreview,
} from '@/types/domain';
import { statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

function isBillPreview(preview: ImportJob['preview']): preview is PurchaseBillPreview {
  return !!preview && !Array.isArray(preview) && Array.isArray((preview as PurchaseBillPreview).lines);
}

// Bill Import Redesign Plan §7 Phase 0: unread OCR fields must render as
// genuinely blank, never a fabricated default like qty=1 or GST=18 — a
// fabricated default is indistinguishable from a real read and hides
// exactly the rows that need the user's attention.
function billedFromPack(cs?: string, pcs?: string, upc?: string): string | null {
  const u = Number(upc);
  if (!Number.isFinite(u) || u <= 0) return null;
  const c = Number(cs || 0);
  const p = Number(pcs || 0);
  if (!Number.isFinite(c) || !Number.isFinite(p)) return null;
  return String(c * u + p);
}

function toPreviewLines(preview: PurchaseBillPreview | null): PurchaseBillLinePreview[] {
  if (!preview?.lines) return [];
  return preview.lines.map((line, index) => {
    const raw = line as PurchaseBillLinePreview & {
      hsn_code?: string;
      unit_price?: string;
      gst_rate?: string;
    };
    return {
      si: raw.si ? String(raw.si) : String(index + 1),
      name: raw.name ?? '',
      sku: raw.sku ?? '',
      hsnCode: raw.hsnCode ?? raw.hsn_code ?? '',
      quantity: raw.quantity != null ? String(raw.quantity) : '',
      pcs: raw.pcs != null && raw.pcs !== '' ? String(raw.pcs) : '',
      cs: raw.cs != null && raw.cs !== '' ? String(raw.cs) : '',
      upc: raw.upc != null && raw.upc !== '' ? String(raw.upc) : '',
      unitPrice:
        raw.unitPrice != null
          ? String(raw.unitPrice)
          : raw.unit_price != null
            ? String(raw.unit_price)
            : '',
      gstRate:
        raw.gstRate != null
          ? String(raw.gstRate)
          : raw.gst_rate != null
            ? String(raw.gst_rate)
            : '',
      mrp: raw.mrp != null ? String(raw.mrp) : '',
      include: raw.include !== false,
      flags: Array.isArray(raw.flags) ? raw.flags : [],
    };
  });
}

export interface BillUploadPageProps {
  kind: Extract<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>;
  canAccess: boolean;
}

export function BillUploadPage({ kind, canAccess }: BillUploadPageProps) {
  const isSales = kind === 'SALES_BILL';
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const partyQuery = useQuery<Array<{ id: number; name: string }>>({
    queryKey: [isSales ? 'customers' : 'suppliers'],
    queryFn: () => (isSales ? listCustomers() : listSuppliers()),
  });

  const [uploadMode, setUploadMode] = useState<'photo' | 'structured'>('photo');
  const [file, setFile] = useState<File | null>(null);
  const [partyId, setPartyId] = useState<number | ''>('');
  const [jobId, setJobId] = useState<number | null>(null);
  const [lines, setLines] = useState<PurchaseBillLinePreview[]>([]);
  const [billNumber, setBillNumber] = useState('');
  const [billDate, setBillDate] = useState('');
  const [piiConsent, setPiiConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showFlaggedOnly, setShowFlaggedOnly] = useState(false);

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
    setLines(toPreviewLines(job.preview));
    setBillNumber(job.preview.billNumber ?? '');
    setBillDate(job.preview.billDate ?? '');
    const party = isSales ? job.customer : job.supplier;
    if (party) setPartyId(party);
  }, [job, isSales]);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose a file');
      return uploadImport(file, kind, {
        supplierId: !isSales && partyId !== '' ? partyId : undefined,
        customerId: isSales && partyId !== '' ? partyId : undefined,
        // A new key each click: the same WhatsApp JPEG must be allowed to
        // re-extract after a prior job was previewed or committed.
        idempotencyKey: newIdempotencyKey(),
      });
    },
    onMutate: () => {
      setJobId(null);
      setLines([]);
      setError(null);
      setSuccessMsg(null);
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

  const clarifyMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) throw new Error('No job');
      return answerImportClarifications(jobId, clarificationAnswers);
    },
    onSuccess: () => {
      setError(null);
      void jobQuery.refetch();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) throw new Error('No job');
      const payloadLines = lines.map((line) => ({
        si: line.si ?? '',
        name: line.name,
        sku: line.sku ?? '',
        hsnCode: line.hsnCode ?? '',
        quantity: line.quantity,
        pcs: line.pcs ?? '',
        cs: line.cs ?? '',
        upc: line.upc ?? '',
        unitPrice: line.unitPrice,
        gstRate: line.gstRate,
        mrp: line.mrp ?? '0',
        include: line.include !== false,
      }));
      await updateImportPreview(jobId, {
        supplierId: !isSales ? (partyId === '' ? null : partyId) : undefined,
        customerId: isSales ? (partyId === '' ? null : partyId) : undefined,
        billNumber,
        billDate,
        lines: payloadLines,
      });
      return commitImport(
        jobId,
        {
          billNumber,
          billDate,
          lines: payloadLines,
        },
        { idempotencyKey: commitKeyRef.current.key || undefined },
      );
    },
    onSuccess: (result) => {
      const purchaseId =
        'purchaseInvoiceId' in result ? (result as PurchaseBillCommitResult).purchaseInvoiceId : undefined;
      const salesId =
        'salesInvoiceId' in result ? (result as PurchaseBillCommitResult).salesInvoiceId : undefined;
      setSuccessMsg(t(isSales ? 'billUpload.successSales' : 'billUpload.success'));
      setError(null);
      if (salesId) {
        void navigate(`/sales/history/${salesId}/edit`, {
          replace: true,
          state: { fromBillUpload: true },
        });
      } else if (purchaseId) {
        void navigate(`/purchases/history/${purchaseId}/edit`, {
          replace: true,
          state: { fromBillUpload: true },
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

  const includedLines = lines.filter((l) => l.include !== false);
  const includedCount = includedLines.length;
  // F2-021: every included line must have a name, a positive qty and a
  // non-negative price before the commit is allowed — otherwise blank/zero
  // lines commit as zero-value invoice lines.
  const invalidIncludedCount = includedLines.filter(
    (l) =>
      !String(l.name ?? '').trim() ||
      !(Number(l.quantity) > 0) ||
      !(Number(l.unitPrice) >= 0) ||
      Number.isNaN(Number(l.unitPrice)),
  ).length;
  // one stable idempotency key per job so a retry after the button re-enables
  // doesn't create a second draft.
  const commitKeyRef = useRef<{ jobId: number | null; key: string }>({ jobId: null, key: '' });
  if (jobId != null && commitKeyRef.current.jobId !== jobId) {
    commitKeyRef.current = { jobId, key: `import-commit-${jobId}-${newIdempotencyKey()}` };
  }
  const flaggedIndices = useMemo(
    () => lines.map((l, i) => (l.flags && l.flags.length > 0 ? i : -1)).filter((i) => i >= 0),
    [lines],
  );
  const flaggedSet = useMemo(() => new Set(flaggedIndices), [flaggedIndices]);
  // Keep the printed bill order (SI 1…n). Flagged rows stay in place and
  // highlight in orange — pulling them to the top reordered the invoice.
  const billOrderIndices = useMemo(() => lines.map((_, i) => i), [lines]);
  const visibleIndices = showFlaggedOnly ? flaggedIndices : billOrderIndices;

  const updateLine = (idx: number, patch: Partial<PurchaseBillLinePreview>) => {
    setLines((prev) =>
      prev.map((l, i) => {
        if (i !== idx) return l;
        const next = { ...l, ...patch };
        if ('cs' in patch || 'pcs' in patch || 'upc' in patch) {
          const billed = billedFromPack(next.cs, next.pcs, next.upc);
          if (billed != null) {
            const hasQty = next.quantity != null && String(next.quantity).trim() !== '' && Number(next.quantity) !== 0;
            if (!hasQty) {
              // F2-020: only auto-fill when the quantity is blank.
              next.quantity = billed;
              next.packQtyHint = undefined;
            } else if (Number(billed) !== Number(next.quantity)) {
              // otherwise offer it as a suggestion, don't overwrite.
              next.packQtyHint = billed;
            } else {
              next.packQtyHint = undefined;
            }
          }
        }
        return next;
      }),
    );
  };

  if (!canAccess) return <ForbiddenPage />;

  const clarifications = job?.clarifications ?? [];
  const needsClarification = job?.status === 'NEEDS_CLARIFICATION' && clarifications.length > 0;
  const preview = job && isBillPreview(job.preview) ? job.preview : null;

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t(isSales ? 'billUpload.titleSales' : 'billUpload.title')}</Typography>
      <Typography color="text.secondary">
        {t(isSales ? 'billUpload.subtitleSales' : 'billUpload.subtitle')}
      </Typography>
      <Alert severity="warning">{t('billUpload.aiAccuracyDisclaimer')}</Alert>
      <Alert severity="info">{t(isSales ? 'billUpload.piiDisclaimerSales' : 'billUpload.piiDisclaimer')}</Alert>
      {error ? <HelpErrorAlert message={error} /> : null}
      {successMsg ? <Alert severity="success">{successMsg}</Alert> : null}
      {job?.status === 'COMMITTED' ? (
        <Alert severity="info">{t('billUpload.alreadyCommitted')}</Alert>
      ) : null}
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
                    void retryImportExtract(jobId).then(() => void jobQuery.refetch());
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
          <ToggleButtonGroup
            size="small"
            exclusive
            value={uploadMode}
            onChange={(_e, next) => {
              if (next) {
                setUploadMode(next);
                setFile(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
              }
            }}
          >
            <ToggleButton value="photo">{t('billUpload.uploadModePhoto')}</ToggleButton>
            <ToggleButton value="structured">{t('billUpload.uploadModeStructured')}</ToggleButton>
          </ToggleButtonGroup>
          {uploadMode === 'structured' ? (
            <Typography variant="body2" color="text.secondary">
              {t('billUpload.uploadModeHint')}
            </Typography>
          ) : null}

          <TextField
            select
            label={t(isSales ? 'billUpload.customerHint' : 'billUpload.supplierHint')}
            value={partyId === '' ? '' : String(partyId)}
            onChange={(e) => setPartyId(e.target.value === '' ? '' : Number(e.target.value))}
            sx={{ maxWidth: 420 }}
          >
            <MenuItem value="">— Auto from bill / create —</MenuItem>
            {(partyQuery.data ?? []).map((p) => (
              <MenuItem key={p.id} value={String(p.id)}>
                {p.name}
              </MenuItem>
            ))}
          </TextField>

          <input
            ref={fileInputRef}
            type="file"
            accept={
              uploadMode === 'structured'
                ? '.csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                : '.pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/*'
            }
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
            {t(uploadMode === 'structured' ? 'billUpload.chooseFileStructured' : 'billUpload.chooseFile')}
          </Button>
          {file ? <Typography variant="body2">Selected: {file.name}</Typography> : null}

          <FormControlLabel
            control={<Checkbox checked={piiConsent} onChange={(e) => setPiiConsent(e.target.checked)} />}
            label={t('billUpload.piiConfirm')}
          />

          <Button
            variant="contained"
            disabled={!file || !piiConsent || extracting}
            onClick={() => uploadMutation.mutate()}
            startIcon={extracting ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            {extracting ? t('billUpload.extracting') : t('common.upload')}
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

      {needsClarification ? (
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="h6">{t('billUpload.clarificationsTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('billUpload.clarificationsHint')}
            </Typography>
            {clarifications.map((c) => (
              <TextField
                key={c.field}
                select
                label={c.question}
                value={clarificationAnswers[c.field] ?? ''}
                onChange={(e) =>
                  setClarificationAnswers((prev) => ({ ...prev, [c.field]: e.target.value }))
                }
                sx={{ maxWidth: 480 }}
              >
                {c.options.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </MenuItem>
                ))}
              </TextField>
            ))}
            <Button
              variant="contained"
              disabled={
                clarifications.some((c) => !clarificationAnswers[c.field]) || clarifyMutation.isPending
              }
              onClick={() => clarifyMutation.mutate()}
              sx={{ alignSelf: 'flex-start' }}
            >
              {t('billUpload.clarificationsSubmit')}
            </Button>
          </Stack>
        </Paper>
      ) : null}

      {job?.status === 'PREVIEWED' ? (
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            {preview?.directionWarning ? (
              <Alert severity="warning">
                <strong>{t('billUpload.directionWarning')}:</strong> {preview.directionWarning}
              </Alert>
            ) : null}
            {typeof preview?.printedLineCount === 'number' &&
            preview.printedLineCount > lines.length ? (
              <Alert
                severity="warning"
                action={
                  jobId != null ? (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => {
                        void retryImportExtract(jobId).then(() => void jobQuery.refetch());
                      }}
                    >
                      {t('billUpload.retryExtract')}
                    </Button>
                  ) : undefined
                }
              >
                {t('billUpload.truncatedLines', {
                  got: lines.length,
                  expected: preview.printedLineCount,
                })}
              </Alert>
            ) : lines.length >= 18 && lines.length <= 22 ? (
              <Alert
                severity="info"
                action={
                  jobId != null ? (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => {
                        void retryImportExtract(jobId).then(() => void jobQuery.refetch());
                      }}
                    >
                      {t('billUpload.retryExtract')}
                    </Button>
                  ) : undefined
                }
              >
                {t('billUpload.maybeTruncated', { got: lines.length })}
              </Alert>
            ) : null}
            {job.billTemplate && clarifications.length === 0 ? (
              <Alert severity="success">{t('billUpload.templateApplied')}</Alert>
            ) : null}
            <Alert severity="warning">{t('billUpload.aiAccuracyDisclaimer')}</Alert>

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
              <>
                <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
                  <Chip
                    size="small"
                    variant="outlined"
                    label={t('billUpload.extractedRows', { count: lines.length })}
                  />
                  <Chip
                    size="small"
                    color={flaggedIndices.length > 0 ? 'warning' : 'success'}
                    label={
                      flaggedIndices.length > 0
                        ? t('billUpload.flaggedSummary', {
                            flagged: flaggedIndices.length,
                            total: lines.length,
                          })
                        : t('billUpload.flaggedNone')
                    }
                  />
                  {flaggedIndices.length > 0 ? (
                    <Button
                      size="small"
                      onClick={() => setShowFlaggedOnly((v) => !v)}
                    >
                      {t(showFlaggedOnly ? 'billUpload.showAllRows' : 'billUpload.showFlaggedOnly')}
                    </Button>
                  ) : null}
                  <Button
                    size="small"
                    onClick={() =>
                      setLines((prev) => prev.map((l) => (l.flags?.length ? l : { ...l, include: true })))
                    }
                  >
                    {t('billUpload.bulkAcceptClean')}
                  </Button>
                  {flaggedIndices.length > 0 ? (
                    <Button
                      size="small"
                      color="warning"
                      onClick={() =>
                        setLines((prev) =>
                          prev.map((l) => (l.flags?.length ? { ...l, include: false } : l)),
                        )
                      }
                    >
                      {t('billUpload.bulkExcludeFlagged')}
                    </Button>
                  ) : null}
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={showAdvanced}
                        onChange={(e) => setShowAdvanced(e.target.checked)}
                      />
                    }
                    label={t('billUpload.advancedColumns')}
                  />
                </Stack>

                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('billUpload.siNo')}</TableCell>
                      <TableCell>{t('billUpload.include')}</TableCell>
                      <TableCell>{t('common.name')}</TableCell>
                      {showAdvanced ? <TableCell>{t('common.sku')}</TableCell> : null}
                      {showAdvanced ? <TableCell>HSN</TableCell> : null}
                      <TableCell align="right">{t('billUpload.colCs')}</TableCell>
                      <TableCell align="right">{t('billUpload.colPcs')}</TableCell>
                      <TableCell align="right">{t('billUpload.colUpc')}</TableCell>
                      <TableCell align="right">{t('billing.qty')}</TableCell>
                      <TableCell align="right">{t('billing.price')}</TableCell>
                      <TableCell align="right">GST %</TableCell>
                      <TableCell align="right">{t('billUpload.mrp')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {visibleIndices.map((idx) => {
                      const line = lines[idx];
                      const isFlagged = flaggedSet.has(idx);
                      const expanded = isFlagged || expandedRows.has(idx);
                      if (!expanded) {
                        return (
                          <TableRow
                            key={idx}
                            hover
                            // F2-047: the collapsed row expands on click — make it
                            // reachable and operable from the keyboard too.
                            role="button"
                            tabIndex={0}
                            aria-expanded={false}
                            aria-label={t('billUpload.expandRow')}
                            sx={{ cursor: 'pointer' }}
                            onClick={() => setExpandedRows((prev) => new Set(prev).add(idx))}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                setExpandedRows((prev) => new Set(prev).add(idx));
                              }
                            }}
                          >
                            <TableCell>{line.si || idx + 1}</TableCell>
                            <TableCell padding="checkbox">
                              <Checkbox
                                checked={line.include !== false}
                                onClick={(e) => e.stopPropagation()}
                                onChange={(e) => updateLine(idx, { include: e.target.checked })}
                              />
                            </TableCell>
                            <TableCell colSpan={showAdvanced ? 3 : 1}>{line.name}</TableCell>
                            <TableCell align="right">{line.cs || '—'}</TableCell>
                            <TableCell align="right">{line.pcs || '—'}</TableCell>
                            <TableCell align="right">{line.upc || '—'}</TableCell>
                            <TableCell align="right">{line.quantity || '—'}</TableCell>
                            <TableCell align="right">{line.unitPrice || '—'}</TableCell>
                            <TableCell align="right">{line.gstRate || '—'}</TableCell>
                            <TableCell align="right">{line.mrp || '—'}</TableCell>
                          </TableRow>
                        );
                      }
                      return (
                        <TableRow key={idx} sx={isFlagged ? { bgcolor: 'warning.light' } : undefined}>
                          <TableCell>{line.si || idx + 1}</TableCell>
                          <TableCell padding="checkbox">
                            <Checkbox
                              checked={line.include !== false}
                              onChange={(e) => updateLine(idx, { include: e.target.checked })}
                            />
                          </TableCell>
                          <TableCell>
                            <Stack spacing={0.5}>
                              <TextField
                                size="small"
                                value={line.name}
                                onChange={(e) => updateLine(idx, { name: e.target.value })}
                              />
                              {(line.flags ?? []).map((flag, fi) => (
                                <Typography key={fi} variant="caption" color="warning.dark">
                                  {t('billUpload.rowFlagged')}: {flag}
                                </Typography>
                              ))}
                            </Stack>
                          </TableCell>
                          {showAdvanced ? (
                            <TableCell>
                              <TextField
                                size="small"
                                value={line.sku ?? ''}
                                onChange={(e) => updateLine(idx, { sku: e.target.value })}
                              />
                            </TableCell>
                          ) : null}
                          {showAdvanced ? (
                            <TableCell>
                              <TextField
                                size="small"
                                value={line.hsnCode ?? ''}
                                onChange={(e) => updateLine(idx, { hsnCode: e.target.value })}
                              />
                            </TableCell>
                          ) : null}
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.cs ?? ''}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { cs: e.target.value })}
                              sx={{ width: 72 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.pcs ?? ''}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { pcs: e.target.value })}
                              sx={{ width: 72 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.upc ?? ''}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { upc: e.target.value })}
                              sx={{ width: 72 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.quantity}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { quantity: e.target.value })}
                              sx={{ width: 90 }}
                            />
                            {line.packQtyHint ? (
                              <Typography
                                variant="caption"
                                color="warning.main"
                                sx={{ display: 'block', cursor: 'pointer', mt: 0.25 }}
                                onClick={() =>
                                  updateLine(idx, { quantity: line.packQtyHint, packQtyHint: undefined })
                                }
                              >
                                pack = {line.packQtyHint} · apply
                              </Typography>
                            ) : null}
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.unitPrice}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { unitPrice: e.target.value })}
                              sx={{ width: 110 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.gstRate}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { gstRate: e.target.value })}
                              sx={{ width: 90 }}
                            />
                          </TableCell>
                          <TableCell align="right">
                            <TextField
                              size="small"
                              type="number"
                              value={line.mrp ?? ''}
                              placeholder="—"
                              onChange={(e) => updateLine(idx, { mrp: e.target.value })}
                              sx={{ width: 100 }}
                            />
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </>
            )}

            <Box>
              <Button
                variant="contained"
                color="secondary"
                disabled={
                  includedCount === 0 ||
                  invalidIncludedCount > 0 ||
                  commitMutation.isPending
                }
                onClick={() => commitMutation.mutate()}
              >
                {t(isSales ? 'billUpload.commitDraftSales' : 'billUpload.commitDraft')}
              </Button>
              {invalidIncludedCount > 0 ? (
                <Typography variant="caption" color="error" sx={{ display: 'block', mt: 0.5 }}>
                  {invalidIncludedCount} included line(s) need a name, a quantity &gt; 0 and a valid price.
                </Typography>
              ) : null}
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t(isSales ? 'billUpload.commitDraftHintSales' : 'billUpload.commitDraftHint')}
              </Typography>
            </Box>
          </Stack>
        </Paper>
      ) : null}
    </Stack>
  );
}
