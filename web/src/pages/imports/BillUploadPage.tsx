import { useCallback, useEffect, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogContentText from '@mui/material/DialogContentText';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage, newIdempotencyKey } from '@/api/client';
import {
  answerImportClarifications,
  cancelImport,
  getImportJob,
  retryImportExtract,
  uploadImport,
  voidImport,
} from '@/api/resources';
import { StatusChip } from '@/components/StatusChip';
import { useCustomerSearch, useSupplierSearch } from '@/hooks/usePartySearch';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import type { Customer, ImportKind, Supplier } from '@/types/domain';
import { toCsv } from '@/utils/csv';
import { statusLabelKey } from '@/utils/status';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { recordExtractionSeconds, typicalExtractionMinutes } from './extractionTimes';
import { BillReviewPanel } from './bill/BillReviewPanel';
import { RecentBillUploads } from './bill/RecentBillUploads';
import { SourceBillViewer } from './bill/SourceBillViewer';
import { isBillPreview } from './bill/billLines';
import { useSourceVisibility } from './bill/useSourceVisibility';

const STILL_WORKING_MS = 180_000;
const STALE_HEARTBEAT_MS = 120_000;

const PHOTO_EXT = /\.(pdf|png|jpe?g|webp|gif)$/i;
const STRUCTURED_EXT = /\.(csv|xlsx|xlsm)$/i;

const CONSENT_KEY = 'bizboard:billUpload:aiConsent';

function readStoredConsent(): boolean {
  try {
    return localStorage.getItem(CONSENT_KEY) === '1';
  } catch {
    return false;
  }
}

function storeConsent(on: boolean): void {
  try {
    if (on) localStorage.setItem(CONSENT_KEY, '1');
    else localStorage.removeItem(CONSENT_KEY);
  } catch {
    // Private mode: the tick is simply asked again next time.
  }
}

/** Header names the structured importer understands (see imports/services.py BILL_COLUMN_ALIASES). */
const SAMPLE_CSV_ROWS: string[][] = [
  ['name', 'sku', 'hsn_code', 'quantity', 'unit_price', 'gst_rate'],
  ['Sample item', 'ITEM-001', '1006', '10', '125.50', '5'],
];

function downloadSampleCsv(): void {
  const url = URL.createObjectURL(new Blob([toCsv(SAMPLE_CSV_ROWS)], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'bill-lines-sample.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function fileAllowed(file: File, mode: 'photo' | 'structured'): boolean {
  if (mode === 'structured') return STRUCTURED_EXT.test(file.name);
  return PHOTO_EXT.test(file.name) || file.type.startsWith('image/') || file.type === 'application/pdf';
}

export interface BillUploadPageProps {
  kind: Extract<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>;
  canAccess: boolean;
}

export function BillUploadPage({ kind, canAccess }: BillUploadPageProps) {
  const isSales = kind === 'SALES_BILL';
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // The job lives in the URL so a refresh, a Back from the draft, or a shared
  // link brings the same review back instead of losing it.
  const jobId = Number(searchParams.get('job')) || null;
  const setJobId = useCallback(
    (id: number | null) => {
      const next = new URLSearchParams(searchParams);
      if (id == null) next.delete('job');
      else next.set('job', String(id));
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const [uploadMode, setUploadMode] = useState<'photo' | 'structured'>('photo');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [party, setParty] = useState<Customer | Supplier | null>(null);
  const partyId = party?.id ?? '';
  const customerSearch = useCustomerSearch({ selected: isSales ? (party as Customer | null) : undefined });
  const supplierSearch = useSupplierSearch({ selected: !isSales ? (party as Supplier | null) : undefined });
  const partySearch = isSales ? customerSearch : supplierSearch;
  const [piiConsent, setPiiConsent] = useState(() => readStoredConsent());
  const [consentWasSaved, setConsentWasSaved] = useState(() => readStoredConsent());
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [reloadToken, setReloadToken] = useState(0);
  const [undoDialog, setUndoDialog] = useState(false);
  const [committedMenu, setCommittedMenu] = useState<HTMLElement | null>(null);
  // When this browser saw each upload start, so finishing can be timed (H-07).
  const startedAt = useRef<Record<number, number>>({});
  const [showSource, setShowSource] = useSourceVisibility();
  const [now, setNow] = useState(() => Date.now());

  const jobQuery = useQuery({
    queryKey: ['import-job', jobId],
    queryFn: () => getImportJob(jobId!),
    enabled: jobId != null,
    retry: false,
    // Back off while a long extraction runs instead of polling every 1.5s for 10 minutes.
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      if (status === 'UPLOADED' || status === 'EXTRACTING') {
        return Math.min(5000, 1500 + q.state.dataUpdateCount * 250);
      }
      return false;
    },
  });
  const job = jobQuery.data;
  const jobMissing = jobQuery.isError && jobId != null;

  const resetAll = useCallback(() => {
    setJobId(null);
    setFile(null);
    setError(null);
    setNotice(null);
    setParty(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [setJobId]);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error(t('billUpload.chooseFileFirst'));
      return uploadImport(file, kind, {
        supplierId: !isSales && partyId !== '' ? partyId : undefined,
        customerId: isSales && partyId !== '' ? partyId : undefined,
        // A new key each click: the same WhatsApp JPEG must be allowed to
        // re-extract after a prior job was previewed or committed.
        idempotencyKey: newIdempotencyKey(),
        aiConsent: uploadMode === 'photo' && piiConsent,
      });
    },
    onMutate: () => {
      setError(null);
      setNotice(null);
    },
    onSuccess: (data) => {
      if (uploadMode === 'photo' && piiConsent) {
        storeConsent(true);
        setConsentWasSaved(true);
      }
      queryClient.setQueryData(['import-job', data.id], data);
      startedAt.current[data.id] = Date.now();
      setJobId(data.id);
      if (data.status === 'FAILED') setError(data.failureReason || t('billUpload.extractionFailed'));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const clarifyMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) throw new Error(t('billUpload.noJob'));
      return answerImportClarifications(jobId, clarificationAnswers);
    },
    onSuccess: () => {
      setError(null);
      void jobQuery.refetch();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelImport(jobId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['recent-bill-uploads', kind] });
      void jobQuery.refetch();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  // A failed retry must say so; otherwise the page looks frozen on the old banner.
  const retryExtract = () => {
    if (jobId == null) return;
    setError(null);
    retryImportExtract(jobId)
      .then(() => void jobQuery.refetch())
      .catch((err) => setError(t('billUpload.retryFailed', { reason: getErrorMessage(err) })));
  };

  const undoImportMutation = useMutation({
    mutationFn: () => voidImport(jobId!),
    onSuccess: () => {
      setUndoDialog(false);
      setNotice(t('billUpload.undone'));
      void jobQuery.refetch();
    },
    onError: (err) => {
      setUndoDialog(false);
      setError(getErrorMessage(err));
    },
  });

  const acceptFile = useCallback(
    (next: File | null) => {
      if (next && !fileAllowed(next, uploadMode)) {
        setError(
          t('billUpload.wrongFileType', {
            types: uploadMode === 'structured' ? 'CSV / XLSX' : 'PDF / PNG / JPG / WEBP',
          }),
        );
        return;
      }
      setFile(next);
      setError(null);
    },
    [uploadMode],
  );

  // Paste a screenshot or photo straight from the clipboard.
  useEffect(() => {
    if (jobId != null || uploadMode !== 'photo') return undefined;
    const onPaste = (event: ClipboardEvent) => {
      const pasted = event.clipboardData?.files?.[0];
      if (pasted) acceptFile(pasted);
    };
    window.addEventListener('paste', onPaste);
    return () => window.removeEventListener('paste', onPaste);
  }, [jobId, uploadMode, acceptFile]);

  useEffect(() => {
    if (!job) return;
    const began = startedAt.current[job.id];
    if (began && job.status !== 'UPLOADED' && job.status !== 'EXTRACTING') {
      delete startedAt.current[job.id];
      if (job.status === 'PREVIEWED' || job.status === 'NEEDS_CLARIFICATION') {
        recordExtractionSeconds((Date.now() - began) / 1000);
      }
    }
  }, [job]);

  const extracting =
    uploadMutation.isPending ||
    job?.status === 'UPLOADED' ||
    job?.status === 'EXTRACTING' ||
    (jobId != null && jobQuery.isLoading);

  // Tick while a job is extracting so the "still working" prompt appears.
  useEffect(() => {
    if (!extracting) return undefined;
    const id = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, [extracting]);

  if (!canAccess) return <ForbiddenPage />;

  // A link to a job of the other direction must not be edited with this screen's fields.
  if (job && job.kind !== kind) {
    const otherPath = job.kind === 'SALES_BILL' ? '/sales/bill-upload' : '/purchases/bill-upload';
    return (
      <Stack spacing={2}>
        <PageTitle>{t(isSales ? 'billUpload.titleSales' : 'billUpload.title')}</PageTitle>
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" component={RouterLink} to={`${otherPath}?job=${job.id}`}>
              {t(job.kind === 'SALES_BILL' ? 'billUpload.openInSales' : 'billUpload.openInPurchases')}
            </Button>
          }
        >
          {t('billUpload.wrongDirectionJob')}
        </Alert>
      </Stack>
    );
  }

  const elapsedMs = job?.createdAt ? now - new Date(job.createdAt).getTime() : 0;
  const heartbeatAge = job?.extractionHeartbeatAt ? now - new Date(job.extractionHeartbeatAt).getTime() : 0;
  const clarifications = job?.clarifications ?? [];
  const needsClarification = job?.status === 'NEEDS_CLARIFICATION' && clarifications.length > 0;
  const needsPiiConsent = uploadMode === 'photo';
  const draftId = isSales ? job?.salesInvoice : job?.purchaseInvoice;
  const draftPath = draftId ? `${isSales ? '/sales/history' : '/purchases/history'}/${draftId}/edit` : null;

  return (
    <Stack spacing={2}>
      <PageTitle>{t(isSales ? 'billUpload.titleSales' : 'billUpload.title')}</PageTitle>
      <Typography color="text.secondary">{t(isSales ? 'billUpload.subtitleSales' : 'billUpload.subtitle')}</Typography>
      {!job && !jobMissing ? (
        consentWasSaved && uploadMode === 'photo' ? (
          <Typography variant="caption" color="text.secondary">
            {t('billUpload.aiConsentSaved')}{' '}
            <Button
              size="small"
              sx={{ p: 0, minWidth: 0, verticalAlign: 'baseline' }}
              onClick={() => {
                storeConsent(false);
                setConsentWasSaved(false);
                setPiiConsent(false);
              }}
            >
              {t('billUpload.aiConsentAskAgain')}
            </Button>
          </Typography>
        ) : (
          <Alert severity="info">
            {t(isSales ? 'billUpload.piiDisclaimerSales' : 'billUpload.piiDisclaimer')} {t('billUpload.aiDisclosure')}
          </Alert>
        )
      ) : null}
      {error ? <HelpErrorAlert message={error} /> : null}
      {notice ? (
        <Alert severity="info" onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      ) : null}
      {jobMissing ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={resetAll}>
              {t('billUpload.reset')}
            </Button>
          }
        >
          {t('billUpload.jobNotFound')}
        </Alert>
      ) : null}

      {job?.status === 'COMMITTED' ? (
        <Alert
          severity="success"
          action={
            <Stack direction="row" spacing={1}>
              {draftPath ? (
                <Button
                  color="inherit"
                  variant="outlined"
                  size="small"
                  component={RouterLink}
                  to={draftPath}
                  state={{ fromBillUpload: true, importJobId: jobId }}
                >
                  {t('billUpload.openDraft')}
                </Button>
              ) : null}
              <Button color="inherit" size="small" onClick={resetAll}>
                {t('billUpload.uploadAnother')}
              </Button>
              <IconButton
                color="inherit"
                size="small"
                aria-label={t('billUpload.moreActions')}
                onClick={(e) => setCommittedMenu(e.currentTarget)}
              >
                <MoreVertIcon fontSize="small" />
              </IconButton>
              <Menu anchorEl={committedMenu} open={Boolean(committedMenu)} onClose={() => setCommittedMenu(null)}>
                <MenuItem
                  onClick={() => {
                    setCommittedMenu(null);
                    setUndoDialog(true);
                  }}
                >
                  {t('billUpload.undoImport')}
                </MenuItem>
              </Menu>
            </Stack>
          }
        >
          {t('billUpload.committedBanner')}
        </Alert>
      ) : null}
      {job?.status === 'CANCELLED' || job?.status === 'VOIDED' ? (
        <Alert
          severity="info"
          action={
            <Button color="inherit" size="small" onClick={resetAll}>
              {t('billUpload.reset')}
            </Button>
          }
        >
          {t('billUpload.cancelled')}
        </Alert>
      ) : null}
      {job?.status === 'FAILED' && job.failureReason ? (
        <Alert
          severity="error"
          action={
            <Stack direction="row" spacing={1}>
              <Button
                color="inherit"
                size="small"
                onClick={retryExtract}
              >
                {t('billUpload.retryExtract')}
              </Button>
              <Button color="inherit" size="small" onClick={resetAll}>
                {t('billUpload.reset')}
              </Button>
            </Stack>
          }
        >
          {job.failureReason}
        </Alert>
      ) : null}

      {jobId == null ? (
        <>
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
                <ToggleButton value="structured">
                  {t(isSales ? 'billUpload.uploadModeStructuredSales' : 'billUpload.uploadModeStructured')}
                </ToggleButton>
              </ToggleButtonGroup>
              <Typography variant="body2" color="text.secondary">
                {t(uploadMode === 'structured' ? 'billUpload.uploadModeHint' : 'billUpload.aiDisclosure')}
              </Typography>

              <Autocomplete
                options={partySearch.options}
                getOptionLabel={(o: Customer | Supplier) => o.name}
                isOptionEqualToValue={(o, v) => o.id === v.id}
                value={party}
                onChange={(_, v) => setParty(v)}
                onInputChange={(_, v) => partySearch.setQuery(v)}
                filterOptions={(opts) => opts}
                loading={partySearch.isFetching}
                sx={{ maxWidth: 420 }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t(isSales ? 'billUpload.customerHint' : 'billUpload.supplierHint')}
                    placeholder={t('billUpload.partyAuto')}
                    helperText={!partySearch.enabled ? t('common.typeToSearch') : undefined}
                  />
                )}
              />

              <input
                ref={fileInputRef}
                type="file"
                accept={
                  uploadMode === 'structured'
                    ? '.csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    : '.pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/*'
                }
                style={{ display: 'none' }}
                onChange={(e) => acceptFile(e.target.files?.[0] ?? null)}
              />
              <Box
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  acceptFile(e.dataTransfer.files?.[0] ?? null);
                }}
                sx={{
                  border: '2px dashed',
                  borderColor: dragging ? 'primary.main' : 'divider',
                  borderRadius: 1,
                  p: 2,
                  textAlign: 'center',
                  bgcolor: dragging ? 'action.hover' : undefined,
                }}
              >
                <Stack spacing={1} alignItems="center">
                  <Typography variant="body2" color="text.secondary">
                    {t('billUpload.dropHere')}
                  </Typography>
                  <Button variant="outlined" onClick={() => fileInputRef.current?.click()}>
                    {t(uploadMode === 'structured' ? 'billUpload.chooseFileStructured' : 'billUpload.chooseFile')}
                  </Button>
                  {file ? <Typography variant="body2">{t('billUpload.selectedFile', { name: file.name })}</Typography> : null}
                </Stack>
              </Box>

              {uploadMode === 'structured' ? (
                <Button size="small" onClick={downloadSampleCsv} sx={{ alignSelf: 'flex-start' }}>
                  {t('billUpload.sampleCsv')}
                </Button>
              ) : null}

              {needsPiiConsent && !consentWasSaved ? (
                <FormControlLabel
                  control={<Checkbox checked={piiConsent} onChange={(e) => setPiiConsent(e.target.checked)} />}
                  label={t('billUpload.piiConfirmAi')}
                />
              ) : null}

              <Button
                variant="contained"
                disabled={!file || (needsPiiConsent && !piiConsent) || extracting}
                onClick={() => uploadMutation.mutate()}
                startIcon={extracting ? <CircularProgress size={16} color="inherit" aria-label={t('common.loading')} /> : undefined}
                sx={{ alignSelf: 'flex-start' }}
              >
                {extracting ? t('billUpload.extracting') : t('common.upload')}
              </Button>
            </Stack>
          </Paper>
          <RecentBillUploads kind={kind} onResume={(id) => setJobId(id)} />
        </>
      ) : null}

      {extracting && jobId != null ? (
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center">
            <CircularProgress size={22} aria-label={t('common.loading')} />
            <Typography>{t('billUpload.extracting')}</Typography>
            {job ? <StatusChip tone="info" labelKey={statusLabelKey(job.status)} /> : null}
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" color="text.secondary">
              {(() => {
                const typical = typicalExtractionMinutes();
                return typical
                  ? t('billUpload.extractHintTypical', { minutes: typical.minutes, count: typical.samples })
                  : t('billUpload.extractHint');
              })()}
            </Typography>
            {elapsedMs <= STILL_WORKING_MS ? (
              <Button size="small" color="inherit" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                {t('billUpload.cancelExtract')}
              </Button>
            ) : null}
          </Stack>
          {elapsedMs > STILL_WORKING_MS ? (
            <Alert
              severity="info"
              action={
                <Stack direction="row" spacing={1}>
                  {heartbeatAge > STALE_HEARTBEAT_MS ? (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={retryExtract}
                    >
                      {t('billUpload.retryExtract')}
                    </Button>
                  ) : null}
                  <Button color="inherit" size="small" disabled={cancelMutation.isPending} onClick={() => cancelMutation.mutate()}>
                    {t('billUpload.cancelExtract')}
                  </Button>
                </Stack>
              }
            >
              {t('billUpload.stillWorking')}
            </Alert>
          ) : null}
        </Stack>
      ) : null}

      {needsClarification && jobId != null ? (
        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr', lg: showSource ? 'minmax(300px, 2fr) 3fr' : '1fr' },
            alignItems: 'start',
          }}
        >
          {showSource ? <SourceBillViewer key={jobId} jobId={jobId} /> : null}
          <Paper sx={{ p: 2 }}>
            <Stack spacing={2}>
              <Button size="small" sx={{ alignSelf: 'flex-start' }} onClick={() => setShowSource(!showSource)}>
                {t(showSource ? 'billUpload.hideSource' : 'billUpload.showSource')}
              </Button>
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
                  onChange={(e) => setClarificationAnswers((prev) => ({ ...prev, [c.field]: e.target.value }))}
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
                disabled={clarifications.some((c) => !clarificationAnswers[c.field]) || clarifyMutation.isPending}
                onClick={() => clarifyMutation.mutate()}
                sx={{ alignSelf: 'flex-start' }}
              >
                {t('billUpload.clarificationsSubmit')}
              </Button>
            </Stack>
          </Paper>
        </Box>
      ) : null}

      {job?.status === 'PREVIEWED' && isBillPreview(job.preview) ? (
        <BillReviewPanel
          key={`${job.id}:${reloadToken}`}
          kind={kind}
          job={job}
          onStale={() => {
            setNotice(t('billUpload.staleReload'));
            void jobQuery.refetch().then(() => setReloadToken((n) => n + 1));
          }}
          onError={setError}
          onCommittedElsewhere={() => {
            void jobQuery.refetch();
          }}
          onCancelled={() => {
            void jobQuery.refetch();
          }}
        />
      ) : null}

      <Dialog open={undoDialog} onClose={() => setUndoDialog(false)}>
        <DialogTitle>{t('billUpload.undoImportTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>{t('billUpload.undoImportBody')}</DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUndoDialog(false)}>{t('common.cancel')}</Button>
          <Button color="error" disabled={undoImportMutation.isPending} onClick={() => undoImportMutation.mutate()}>
            {t('billUpload.undoImport')}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
