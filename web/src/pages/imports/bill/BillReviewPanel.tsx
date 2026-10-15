import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Snackbar from '@mui/material/Snackbar';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Drawer from '@mui/material/Drawer';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { confirmAction } from '@/utils/confirmBridge';
import {
  cancelImport,
  commitImport,
  getCustomer,
  getImportJob,
  getSupplier,
  retryImportExtract,
  switchImportKind,
  updateImportPreview,
  validateImportBill,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { UnsavedChangesGuard } from '@/components/UnsavedChangesGuard';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { useCustomerSearch, useSupplierSearch } from '@/hooks/usePartySearch';
import { t } from '@/i18n';
import type {
  BillLineError,
  BillValidationReport,
  Customer,
  ImportJob,
  ImportKind,
  PurchaseBillCommitResult,
  PurchaseBillPreview,
  Supplier,
} from '@/types/domain';
import {
  canCreatePurchases,
  canCreateSales,
  canImportPurchaseBill,
  canImportSalesBill,
  canViewPurchaseSurfaces,
  canViewSalesSurfaces,
} from '@/utils/permissions';
import { BillLinesTable } from './BillLinesTable';
import { BillTotalsPanel } from './BillTotalsPanel';
import { PartyBlock } from './PartyBlock';
import { SourceBillViewer } from './SourceBillViewer';
import { useSourceVisibility } from './useSourceVisibility';
import {
  billedFromPack,
  hasPackData,
  isLineComplete,
  linePayload,
  lineSignature,
  localLineErrors,
  newClientKey,
  payloadHash,
  toEditorLines,
  type EditorLine,
} from './billLines';

const AUTOSAVE_MS = 1500;
const RETRY_MS = 8000;

type SaveState = 'idle' | 'saving' | 'saved' | 'failed';
type RowFilter = 'all' | 'flagged' | 'problems';

type ServerDetails = {
  lineErrors?: { row: number; lineId?: number; name: string; errors: BillLineError[] }[];
  headerErrors?: BillLineError[];
};

function serverDetails(err: unknown): ServerDetails | null {
  if (!axios.isAxiosError(err)) return null;
  const data = err.response?.data as { error?: { details?: ServerDetails } } | undefined;
  const details = data?.error?.details;
  return details && (details.lineErrors || details.headerErrors) ? details : null;
}

type Props = {
  kind: Extract<ImportKind, 'PURCHASE_BILL' | 'SALES_BILL'>;
  job: ImportJob;
  /** The server copy changed under us: the container reloads it and remounts this panel. */
  onStale: () => void;
  /** The draft was created but this user cannot open it: refresh to show the committed banner. */
  onCommittedElsewhere: () => void;
  onError: (message: string | null) => void;
  onCancelled: () => void;
};

/**
 * The review screen. All editable state starts from the job the panel is
 * mounted with (the container re-mounts it with a new key when the server
 * copy must replace local edits), so there is no hydrate-in-an-effect step.
 */
export function BillReviewPanel({ kind, job, onStale, onCommittedElsewhere, onError, onCancelled }: Props) {
  const isSales = kind === 'SALES_BILL';
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  useFeatureFlagEpoch();
  const reviewV2 = isRuntimeFlagEnabled('BILL_IMPORT_REVIEW_V2');
  const jobId = job.id;
  const preview = job.preview as PurchaseBillPreview;

  const [initial] = useState(() => ({
    lines: toEditorLines(preview),
    version: preview.previewVersion,
  }));

  const [party, setParty] = useState<Customer | Supplier | null>(null);
  const partyId = party?.id ?? '';
  const customerSearch = useCustomerSearch({ selected: isSales ? (party as Customer | null) : undefined });
  const supplierSearch = useSupplierSearch({ selected: !isSales ? (party as Supplier | null) : undefined });
  const partySearch = isSales ? customerSearch : supplierSearch;

  const [lines, setLinesState] = useState<EditorLine[]>(initial.lines);
  const linesRef = useRef<EditorLine[]>(initial.lines);
  const [lineDirty, setLineDirtyState] = useState<Set<string>>(new Set());
  const lineDirtyRef = useRef<Set<string>>(new Set());
  const [pendingDeletes, setDeletesState] = useState<number[]>([]);
  const deletesRef = useRef<number[]>([]);
  const [headerDirty, setHeaderDirtyState] = useState(false);
  const versionRef = useRef<number | undefined>(initial.version);
  const savePromise = useRef<Promise<boolean> | null>(null);
  const retryableRef = useRef(false);

  const setLines = useCallback((updater: (prev: EditorLine[]) => EditorLine[]) => {
    const next = updater(linesRef.current);
    linesRef.current = next;
    setLinesState(next);
  }, []);
  const setLineDirty = useCallback((updater: (prev: Set<string>) => Set<string>) => {
    const next = updater(lineDirtyRef.current);
    lineDirtyRef.current = next;
    setLineDirtyState(next);
  }, []);
  const setDeletes = useCallback((updater: (prev: number[]) => number[]) => {
    const next = updater(deletesRef.current);
    deletesRef.current = next;
    setDeletesState(next);
  }, []);
  const setHeaderDirty = setHeaderDirtyState;

  const [billNumber, setBillNumber] = useState(preview.billNumber ?? '');
  const [billDate, setBillDate] = useState(preview.billDate ?? '');
  const [partyName, setPartyName] = useState(
    isSales ? preview.customerName || preview.buyerName || '' : preview.supplierName ?? '',
  );
  const [partyGstin, setPartyGstin] = useState(isSales ? preview.buyerGstin ?? '' : preview.supplierGstin ?? '');
  const [priceMode, setPriceMode] = useState<'EXCLUSIVE' | 'INCLUSIVE'>(
    preview.priceMode === 'INCLUSIVE' ? 'INCLUSIVE' : 'EXCLUSIVE',
  );
  const [additionalCharges, setAdditionalCharges] = useState(preview.additionalCharges ?? '');
  const [invoiceDiscount, setInvoiceDiscount] = useState(preview.invoiceDiscount ?? '');
  const [printedTotal, setPrintedTotal] = useState(preview.printedTotal ?? '');
  const [companyGstinId, setCompanyGstinId] = useState<number | null>(preview.companyGstinId ?? null);
  const [confirmNonGst, setConfirmNonGst] = useState(Boolean(preview.confirmNonGst));
  const [confirmDuplicate, setConfirmDuplicate] = useState(Boolean(preview.confirmDuplicate));
  const [confirmNewProducts, setConfirmNewProducts] = useState(Boolean(preview.confirmNewProducts));
  const [lowConfidenceAccepted, setLowConfidenceAccepted] = useState(Boolean(preview.lowConfidenceAccepted));
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [rowFilter, setRowFilter] = useState<RowFilter>('all');
  const [showSource, setShowSource] = useSourceVisibility();
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [saveTick, setSaveTick] = useState(0);
  const [report, setReport] = useState<BillValidationReport | null>(null);
  const [headerErrors, setHeaderErrors] = useState<BillLineError[]>([]);
  const [focusKey, setFocusKey] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const narrow = useMediaQuery('(max-width:1199.95px)');
  const [lastDeleted, setLastDeleted] = useState<EditorLine | null>(null);
  const [undoOpen, setUndoOpen] = useState(false);
  const [announce] = useState(() =>
    t('billUpload.rowsRead', {
      count: initial.lines.length,
      flagged: initial.lines.filter((l) => (l.flags?.length ?? 0) > 0).length,
    }),
  );

  // Header values, mirrored for the timers / awaited saves that build payloads.
  const header = {
    billNumber, billDate, partyName, partyGstin, priceMode, additionalCharges, invoiceDiscount,
    printedTotal, companyGstinId, confirmNonGst, confirmDuplicate, confirmNewProducts,
    lowConfidenceAccepted, partyId,
  };
  const headerRef = useRef(header);
  useEffect(() => {
    headerRef.current = header;
  });
  const headerSig = JSON.stringify(header);

  // The party the server matched (or the reviewer picked) shows in the picker.
  const detectedPartyId = isSales ? job.customer : job.supplier;
  useEffect(() => {
    if (!detectedPartyId) return undefined;
    let cancelled = false;
    void (isSales ? getCustomer(detectedPartyId) : getSupplier(detectedPartyId))
      .then((p) => {
        if (!cancelled) setParty((current) => current ?? p);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [detectedPartyId, isSales]);

  // The lines a save sends: new ones and edited ones. One definition for the
  // payload and for the bookkeeping that clears them afterwards.
  const collectDirtyLines = useCallback(
    () => linesRef.current.filter((l) => l.lineId == null || lineDirtyRef.current.has(l.clientKey)),
    [],
  );

  const buildPayload = useCallback(() => {
    const h = headerRef.current;
    const dirtyLines = collectDirtyLines();
    return {
      previewVersion: versionRef.current,
      billNumber: h.billNumber,
      billDate: h.billDate,
      ...(isSales
        ? { buyerName: h.partyName, buyerGstin: h.partyGstin, customerId: h.partyId === '' ? null : Number(h.partyId) }
        : { supplierName: h.partyName, supplierGstin: h.partyGstin, supplierId: h.partyId === '' ? null : Number(h.partyId) }),
      priceMode: h.priceMode,
      additionalCharges: h.additionalCharges,
      invoiceDiscount: h.invoiceDiscount,
      printedTotal: h.printedTotal,
      companyGstinId: h.companyGstinId,
      confirmDuplicate: h.confirmDuplicate,
      confirmNewProducts: h.confirmNewProducts,
      confirmNonGst: h.confirmNonGst,
      lowConfidenceAccepted: h.lowConfidenceAccepted,
      lines: [
        ...dirtyLines.map(linePayload),
        ...deletesRef.current.map((lineId) => ({ lineId, deleted: true })),
      ],
    };
  }, [isSales, collectDirtyLines]);

  const applyValidation = useCallback(
    (lineErrors: NonNullable<ServerDetails['lineErrors']>, head: BillLineError[]) => {
      setHeaderErrors(head);
      const byId = new Map(lineErrors.map((e) => [e.lineId, e.errors]));
      setLines((prev) =>
        prev.map((l) => (l.lineId != null && byId.has(l.lineId) ? { ...l, errors: byId.get(l.lineId) } : l)),
      );
      const first = linesRef.current.find((l) => l.lineId != null && byId.has(l.lineId));
      if (first) {
        setExpandedRows((prev) => new Set(prev).add(first.clientKey));
        setFocusKey(first.clientKey);
      }
    },
    [setLines],
  );

  // ------------------------------------------------------------ autosave
  const runSave = useCallback(async (): Promise<boolean> => {
    const sentLines = collectDirtyLines();
    const sentKeys = new Set(sentLines.map((l) => l.clientKey));
    const sentNewKeys = sentLines.filter((l) => l.lineId == null).map((l) => l.clientKey);
    const sentSignatures = new Map(sentLines.map((l) => [l.clientKey, lineSignature(l)]));
    const sentDeletes = [...deletesRef.current];
    const sentHeaderSig = JSON.stringify(headerRef.current);
    const knownIds = new Set(linesRef.current.map((l) => l.lineId).filter((x): x is number => x != null));
    setSaveState('saving');
    try {
      const saved = await updateImportPreview(jobId, buildPayload());
      queryClient.setQueryData(['import-job', jobId], saved);
      const sp = saved.preview as PurchaseBillPreview;
      versionRef.current = sp.previewVersion;
      const byId = new Map(sp.lines.map((l) => [l.lineId, l]));
      // New rows get ascending ids in the order they were sent; sort so a reordered response cannot swap them.
      const unseen = sp.lines
        .filter((l) => l.lineId != null && !knownIds.has(l.lineId))
        .sort((a, b) => (a.lineId as number) - (b.lineId as number));
      let nextNew = 0;
      setLines((prev) =>
        prev.map((l) => {
          let server = l.lineId != null ? byId.get(l.lineId) : undefined;
          if (!server && l.lineId == null && sentNewKeys.includes(l.clientKey)) {
            server = unseen[nextNew];
            nextNew += 1;
          }
          if (!server) return l;
          return {
            ...l,
            lineId: server.lineId,
            errors: server.errors ?? [],
            productMatch: server.productMatch ?? l.productMatch,
            priceListPrice: server.priceListPrice,
            belowPriceList: Boolean(server.belowPriceList),
            cessRate: server.cessRate ?? l.cessRate,
            excludedReason: server.excludedReason,
            flags: server.flags ?? l.flags,
          };
        }),
      );
      setLineDirty((prev) => {
        const next = new Set(prev);
        for (const key of sentKeys) {
          const current = linesRef.current.find((l) => l.clientKey === key);
          if (!current || lineSignature(current) === sentSignatures.get(key)) next.delete(key);
        }
        return next;
      });
      setDeletes((prev) => prev.filter((id) => !sentDeletes.includes(id)));
      if (JSON.stringify(headerRef.current) === sentHeaderSig) setHeaderDirty(false);
      setSaveState('saved');
      return true;
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        // Edited elsewhere: take the server copy (the container remounts us).
        try {
          const fresh = await getImportJob(jobId);
          queryClient.setQueryData(['import-job', jobId], fresh);
          onStale();
        } catch {
          retryableRef.current = true;
          setSaveState('failed');
        }
        return false;
      }
      // A rejected edit (4xx) needs the user to change something; a dropped connection or 5xx is worth retrying.
      retryableRef.current = !axios.isAxiosError(err) || !err.response || err.response.status >= 500;
      setSaveState('failed');
      return false;
    }
  }, [jobId, buildPayload, collectDirtyLines, queryClient, setLines, setLineDirty, setDeletes, setHeaderDirty, onStale]);

  const startSave = useCallback(() => {
    if (savePromise.current) return savePromise.current;
    const promise = runSave()
      .then((ok) => {
        if (ok) setSaveTick((n) => n + 1);
        return ok;
      })
      .finally(() => {
        savePromise.current = null;
      });
    savePromise.current = promise;
    return promise;
  }, [runSave]);

  const hasUnsaved = headerDirty || lineDirty.size > 0 || pendingDeletes.length > 0 || lines.some((l) => l.lineId == null);
  useEffect(() => {
    if (!hasUnsaved) return undefined;
    if (saveState === 'failed' && !retryableRef.current) return undefined;
    const timer = window.setTimeout(
      () => {
        void startSave();
      },
      saveState === 'failed' ? RETRY_MS : AUTOSAVE_MS,
    );
    return () => window.clearTimeout(timer);
  }, [hasUnsaved, saveState, startSave, saveTick, headerSig, lines, lineDirty, pendingDeletes]);

  useEffect(() => {
    if (!hasUnsaved && saveState !== 'failed') return undefined;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = t('billUpload.unsavedLeave');
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [hasUnsaved, saveState]);

  // ------------------------------------------------------------ mutations
  const checkMutation = useMutation({
    mutationFn: async () => {
      if (savePromise.current) await savePromise.current;
      return validateImportBill(jobId, buildPayload());
    },
    onSuccess: (result) => {
      setReport(result);
      applyValidation(result.lineErrors, result.headerErrors);
      onError(null);
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  const commitMutation = useMutation({
    mutationFn: async () => {
      if (savePromise.current) await savePromise.current;
      const payload = buildPayload();
      // The key follows the payload: an edited retry is a new request, an
      // identical retry (lost response) replays the first result.
      return commitImport(jobId, payload, {
        idempotencyKey: `import-commit-${jobId}-${payloadHash(payload)}`,
      });
    },
    onSuccess: (result) => {
      const purchaseId =
        'purchaseInvoiceId' in result ? (result as PurchaseBillCommitResult).purchaseInvoiceId : undefined;
      const salesId =
        'salesInvoiceId' in result ? (result as PurchaseBillCommitResult).salesInvoiceId : undefined;
      const created = 'productsCreated' in result ? (result as PurchaseBillCommitResult).productsCreated : 0;
      onError(null);
      setLineDirty(() => new Set());
      setDeletes(() => []);
      setHeaderDirty(false);
      void queryClient.invalidateQueries({ queryKey: ['recent-bill-uploads', kind] });
      const state = { fromBillUpload: true, importJobId: jobId, productsCreated: created };
      // Push (not replace): Back returns to ?job=, where the committed banner shows.
      // If the person can no longer edit the document (rights changed mid-session), open
      // the read-only page instead of a forbidden one; with neither, stay on the banner.
      if (salesId) {
        if (canCreateSales(user)) void navigate(`/sales/history/${salesId}/edit`, { state });
        else if (canViewSalesSurfaces(user)) void navigate(`/sales/history/${salesId}`, { state });
        else onCommittedElsewhere();
      } else if (purchaseId) {
        if (canCreatePurchases(user)) void navigate(`/purchases/history/${purchaseId}/edit`, { state });
        else if (canViewPurchaseSurfaces(user)) void navigate(`/purchases/history/${purchaseId}`, { state });
        else onCommittedElsewhere();
      }
    },
    onError: async (err) => {
      const details = serverDetails(err);
      if (details) {
        applyValidation(details.lineErrors ?? [], details.headerErrors ?? []);
        onError(getErrorMessage(err));
        return;
      }
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        try {
          const fresh = await getImportJob(jobId);
          queryClient.setQueryData(['import-job', jobId], fresh);
          const freshVersion = (fresh.preview as PurchaseBillPreview).previewVersion;
          if (freshVersion !== versionRef.current) onStale();
          else onError(getErrorMessage(err));
        } catch {
          onError(getErrorMessage(err));
        }
        return;
      }
      onError(getErrorMessage(err));
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelImport(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['recent-bill-uploads', kind] });
      onCancelled();
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  const switchMutation = useMutation({
    mutationFn: () => switchImportKind(jobId, isSales ? 'PURCHASE_BILL' : 'SALES_BILL'),
    onSuccess: () => {
      const target = isSales ? '/purchases/bill-upload' : '/sales/bill-upload';
      void navigate(`${target}?job=${jobId}`);
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  // ------------------------------------------------------------ derived
  const extractionConfidence = Number(preview.extractionConfidence ?? 1);
  const lowConfidence = Number.isFinite(extractionConfidence) && extractionConfidence < 0.7;
  const includedLines = lines.filter((l) => l.include !== false);
  const includedCount = includedLines.length;
  const lineProblems = (l: EditorLine) => {
    const merged = [...(l.errors ?? []).filter((e) => e.severity !== 'warning'), ...localLineErrors(l)];
    if (
      reviewV2 &&
      l.productMatch?.status === 'candidates' &&
      l.productId == null &&
      !l.createNew
    ) {
      merged.push({ field: 'product', code: 'PRODUCT_CHOICE_REQUIRED', message: t('billUpload.productChoose') });
    }
    return merged;
  };
  const invalidIncludedCount = includedLines.filter((l) => lineProblems(l).length > 0).length;
  const allZeroRate = includedCount > 0 && includedLines.every((l) => Number(l.gstRate || 0) === 0);
  const flaggedKeys = lines.filter((l) => (l.flags?.length ?? 0) > 0).map((l) => l.clientKey);
  const problemKeys = includedLines.filter((l) => lineProblems(l).length > 0).map((l) => l.clientKey);
  const visibleKeys = useMemo(() => {
    const all = lines.map((l) => l.clientKey);
    if (rowFilter === 'flagged') return all.filter((k) => flaggedKeys.includes(k));
    if (rowFilter === 'problems') return all.filter((k) => problemKeys.includes(k));
    return all;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, rowFilter]);
  const showPack = showAdvanced || hasPackData(lines);
  const showDiscount = showAdvanced || lines.some((l) => String(l.discountPercent ?? '').trim() !== '');
  const newProductCount = preview.newProductCount ?? 0;
  const gstinStatus = preview.companyGstinStatus;
  const gstinUnresolved = gstinStatus?.status === 'unresolved' && companyGstinId == null;
  const needsDuplicateConfirm =
    headerErrors.some((e) => e.code === 'DUPLICATE_BILL') ||
    Boolean(report?.headerErrors.some((e) => e.code === 'DUPLICATE_BILL'));
  const partyMissing = partyId === '' && !partyName.trim();
  const commitBlocked =
    includedCount === 0 ||
    invalidIncludedCount > 0 ||
    !billDate.trim() ||
    partyMissing ||
    gstinUnresolved ||
    (reviewV2 && newProductCount > 0 && !confirmNewProducts) ||
    (lowConfidence && !lowConfidenceAccepted) ||
    commitMutation.isPending;
  // C-01: say which condition turned the button off, the first one a person should fix.
  const blockerReason = commitMutation.isPending
    ? t('billUpload.blockSaving')
    : partyMissing
      ? t('billUpload.blockNoParty')
      : !billDate.trim()
        ? t('billUpload.blockNoDate')
        : gstinUnresolved
          ? t('billUpload.blockGstin')
          : includedCount === 0
            ? t('billUpload.blockNoRows')
            : invalidIncludedCount > 0
              ? t('billUpload.blockInvalid', { count: invalidIncludedCount })
              : reviewV2 && newProductCount > 0 && !confirmNewProducts
                ? t('billUpload.blockNewProducts')
                : lowConfidence && !lowConfidenceAccepted
                  ? t('billUpload.blockLowConfidence')
                  : '';
  const confirmsNeeded =
    (newProductCount > 0 && reviewV2) || allZeroRate || needsDuplicateConfirm || lowConfidence;
  const canSwitch = isSales ? canImportPurchaseBill(user) : canImportSalesBill(user);
  const sourceVisible = showSource;
  const activeBox = activeKey ? lines.find((l) => l.clientKey === activeKey)?.bbox ?? null : null;
  const saveLabel =
    saveState === 'saving'
      ? t('billUpload.saving')
      : saveState === 'failed'
        ? t('billUpload.saveFailed')
        : saveState === 'saved' && !hasUnsaved
          ? t('billUpload.saved')
          : '';
  const blockingHeaderErrors = (report?.headerErrors ?? headerErrors).filter((e) => e.severity !== 'warning');

  const touchHeader = <T,>(set: (v: T) => void) => (value: T) => {
    set(value);
    setHeaderDirty(true);
  };

  const updateLine = (key: string, patch: Partial<EditorLine>) => {
    setLines((prev) =>
      prev.map((l) => {
        if (l.clientKey !== key) return l;
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
    setLineDirty((prev) => new Set(prev).add(key));
  };

  const addRow = () => {
    const key = newClientKey();
    const row: EditorLine = {
      clientKey: key,
      si: String(linesRef.current.length + 1),
      name: '',
      quantity: '1',
      unitPrice: '0',
      gstRate: '',
      mrp: '',
      include: true,
      flags: [],
      errors: [],
    };
    setLines((prev) => [...prev, row]);
    setExpandedRows((prev) => new Set(prev).add(key));
    setFocusKey(key);
  };

  const deleteRow = (key: string) => {
    const line = linesRef.current.find((l) => l.clientKey === key);
    if (!line) return;
    setLines((prev) => prev.filter((l) => l.clientKey !== key));
    setLineDirty((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (line.lineId != null) setDeletes((prev) => [...prev, line.lineId as number]);
    setLastDeleted(line);
    setUndoOpen(true);
    setHeaderDirty(true);
  };

  const undoDelete = () => {
    const line = lastDeleted;
    if (!line) return;
    if (line.lineId != null && deletesRef.current.includes(line.lineId)) {
      setDeletes((prev) => prev.filter((id) => id !== line.lineId));
      setLines((prev) => [...prev, line]);
      // Edits made before the delete were dropped from the dirty set; send them again.
      setLineDirty((prev) => new Set(prev).add(line.clientKey));
    } else {
      // Already deleted on the server: bring it back as a new row.
      setLines((prev) => [...prev, { ...line, lineId: undefined, clientKey: newClientKey() }]);
    }
    setUndoOpen(false);
  };

  // Scroll the first problem row into view after a failed commit / check.
  useEffect(() => {
    if (!focusKey) return;
    document.getElementById(`bill-row-${focusKey}`)?.scrollIntoView?.({ block: 'center' });
  }, [focusKey, lines.length]);

  return (
    <>
      <Box
        role="status"
        aria-live="polite"
        // In sx, `width: 1` means 100%: spell the pixel size out so the live region takes no room.
        sx={{ position: 'absolute', width: '1px', height: '1px', m: '-1px', p: 0, border: 0, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap' }}
      >
        {announce}
      </Box>
      <UnsavedChangesGuard when={hasUnsaved || saveState === 'failed'} />
      <Stack direction="row" spacing={1} alignItems="center">
        <Button size="small" onClick={() => setShowSource(!showSource)}>
          {t(showSource ? 'billUpload.hideSource' : 'billUpload.showSource')}
        </Button>
        {job.fileName ? (
          <Typography variant="caption" color="text.secondary">
            {job.fileName}
          </Typography>
        ) : null}
      </Stack>
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr', lg: sourceVisible && !narrow ? 'minmax(300px, 2fr) 3fr' : '1fr' },
          alignItems: 'start',
        }}
      >
        {sourceVisible && !narrow ? (
          <SourceBillViewer key={jobId} jobId={jobId} highlight={activeBox} />
        ) : null}

        <Paper sx={{ p: 2, minWidth: 0 }}>
          <Stack spacing={2}>
            {preview.directionWarning ? (
              <Alert
                severity="warning"
                action={
                  canSwitch ? (
                    <Button color="inherit" size="small" disabled={switchMutation.isPending} onClick={() => switchMutation.mutate()}>
                      {t(isSales ? 'billUpload.switchToPurchase' : 'billUpload.switchToSales')}
                    </Button>
                  ) : undefined
                }
              >
                <strong>{t('billUpload.directionWarning')}:</strong> {preview.directionWarning}
              </Alert>
            ) : null}
            {preview.injectionFlagged ? (
              <Alert severity="error">
                <strong>{t('billUpload.injectionWarningTitle')}:</strong> {t('billUpload.injectionWarningBody')}
              </Alert>
            ) : null}
            {typeof preview.printedLineCount === 'number' && preview.printedLineCount > lines.length ? (
              <Alert
                severity="warning"
                action={
                  <Button color="inherit" size="small" onClick={addRow}>
                    {t('billUpload.addRow')}
                  </Button>
                }
              >
                {t('billUpload.truncatedLines', { got: lines.length, expected: preview.printedLineCount })}
              </Alert>
            ) : lines.length >= 18 && lines.length <= 22 ? (
              <Alert
                severity="info"
                action={
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => {
                      retryImportExtract(jobId)
                        .then(() => onStale())
                        .catch((err) => onError(t('billUpload.retryFailed', { reason: getErrorMessage(err) })));
                    }}
                  >
                    {t('billUpload.retryExtract')}
                  </Button>
                }
              >
                {t('billUpload.maybeTruncated', { got: lines.length })}
              </Alert>
            ) : null}
            <Alert severity={!preview.injectionFlagged && (preview.warnings?.length ?? 0) > 0 ? 'warning' : 'info'} variant="outlined">
              {job.billTemplate && (job.clarifications ?? []).length === 0 ? `${t('billUpload.templateApplied')} ` : ''}
              {t('billUpload.aiAccuracyDisclaimer')}
              {!preview.injectionFlagged && preview.warnings && preview.warnings.length > 0 ? (
                <>
                  <strong style={{ display: 'block', marginTop: 4 }}>{t('billUpload.extractionWarningsTitle')}:</strong>
                  <ul style={{ margin: '4px 0 0', paddingLeft: '1.2em' }}>
                    {preview.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </Alert>

            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              <TextField
                label={t('billUpload.billNumber')}
                value={billNumber}
                onChange={(e) => touchHeader(setBillNumber)(e.target.value)}
                sx={{ minWidth: 200 }}
              />
              <TextField
                label={t('billUpload.billDate')}
                type="date"
                InputLabelProps={{ shrink: true }}
                value={billDate}
                onChange={(e) => touchHeader(setBillDate)(e.target.value)}
                error={!billDate.trim()}
                sx={{ minWidth: 200 }}
              />
            </Stack>

            <Autocomplete
              options={partySearch.options}
              getOptionLabel={(o: Customer | Supplier) => o.name}
              isOptionEqualToValue={(o, v) => o.id === v.id}
              value={party}
              onChange={(_, v) => {
                setParty(v);
                setHeaderDirty(true);
              }}
              onInputChange={(_, v) => partySearch.setQuery(v)}
              filterOptions={(opts) => opts}
              loading={partySearch.isFetching}
              sx={{ maxWidth: 420 }}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t(isSales ? 'billUpload.customerHint' : 'billUpload.supplierHint')}
                  helperText={!partySearch.enabled ? t('common.typeToSearch') : undefined}
                />
              )}
            />
            <PartyBlock
              isSales={isSales}
              hasSelectedParty={party != null}
              match={preview.partyMatch}
              name={partyName}
              gstin={partyGstin}
              onNameChange={touchHeader(setPartyName)}
              onGstinChange={touchHeader(setPartyGstin)}
              onPickCandidate={(id) => {
                void (isSales ? getCustomer(id) : getSupplier(id)).then((p) => {
                  setParty(p);
                  setHeaderDirty(true);
                });
              }}
              error={partyMissing ? t('billUpload.partyNeeded') : undefined}
            />

            {gstinStatus?.suggestion && companyGstinId == null ? (
              <Alert
                severity="info"
                action={
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => touchHeader(setCompanyGstinId)(gstinStatus.suggestion!.id)}
                  >
                    {t('billUpload.companyGstinUse')}
                  </Button>
                }
              >
                {t('billUpload.companyGstinSuggest', { gstin: gstinStatus.suggestion.gstin })}
              </Alert>
            ) : null}
            {gstinStatus && gstinStatus.options.length > 1 ? (
              <TextField
                select
                size="small"
                label={t('billUpload.companyGstinLabel')}
                helperText={gstinUnresolved ? t('billUpload.companyGstinHelp') : undefined}
                error={gstinUnresolved}
                value={companyGstinId ?? gstinStatus.resolvedId ?? ''}
                onChange={(e) => touchHeader(setCompanyGstinId)(Number(e.target.value))}
                sx={{ maxWidth: 360 }}
              >
                {gstinStatus.options.map((option) => (
                  <MenuItem key={option.id} value={option.id}>
                    {option.gstin}
                    {option.state ? ` · ${option.state}` : ''}
                  </MenuItem>
                ))}
              </TextField>
            ) : null}

            {lines.length === 0 ? (
              <Alert
                severity="warning"
                action={
                  <Button color="inherit" size="small" onClick={addRow}>
                    {t('billUpload.addRow')}
                  </Button>
                }
              >
                {t('billUpload.noLines')}
              </Alert>
            ) : (
              <>
                <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Chip size="small" variant="outlined" label={t('billUpload.extractedRows', { count: lines.length })} />
                  <Chip
                    size="small"
                    color={flaggedKeys.length > 0 ? 'warning' : 'success'}
                    label={
                      flaggedKeys.length > 0
                        ? t('billUpload.flaggedSummary', { flagged: flaggedKeys.length, total: lines.length })
                        : t('billUpload.flaggedNone')
                    }
                  />
                  {flaggedKeys.length > 0 ? (
                    <Button size="small" onClick={() => setRowFilter((f) => (f === 'flagged' ? 'all' : 'flagged'))}>
                      {t(rowFilter === 'flagged' ? 'billUpload.showAllRows' : 'billUpload.showFlaggedOnly')}
                    </Button>
                  ) : null}
                  {problemKeys.length > 0 ? (
                    <Button size="small" color="error" onClick={() => setRowFilter((f) => (f === 'problems' ? 'all' : 'problems'))}>
                      {t(rowFilter === 'problems' ? 'billUpload.showAllRows' : 'billUpload.showErrorsOnly')}
                    </Button>
                  ) : null}
                  <Button
                    size="small"
                    onClick={() => {
                      // Only rows that are both unflagged and complete: a row
                      // with a blank quantity or GST rate must not be ticked.
                      const toInclude = linesRef.current.filter(
                        (l) => !(l.flags?.length) && l.include === false && isLineComplete(l),
                      );
                      setLines((prev) =>
                        prev.map((l) => (toInclude.some((x) => x.clientKey === l.clientKey) ? { ...l, include: true } : l)),
                      );
                      setLineDirty((prev) => {
                        const next = new Set(prev);
                        toInclude.forEach((l) => next.add(l.clientKey));
                        return next;
                      });
                    }}
                  >
                    {t('billUpload.bulkAcceptClean')}
                  </Button>
                  {flaggedKeys.length > 0 ? (
                    <Button
                      size="small"
                      color="warning"
                      onClick={() => {
                        setLines((prev) => prev.map((l) => (l.flags?.length ? { ...l, include: false } : l)));
                        setLineDirty((prev) => {
                          const next = new Set(prev);
                          flaggedKeys.forEach((k) => next.add(k));
                          return next;
                        });
                      }}
                    >
                      {t('billUpload.bulkExcludeFlagged')}
                    </Button>
                  ) : null}
                  <FormControlLabel
                    control={<Checkbox size="small" checked={showAdvanced} onChange={(e) => setShowAdvanced(e.target.checked)} />}
                    label={t('billUpload.advancedColumns')}
                  />
                </Stack>

                <BillLinesTable
                  lines={lines}
                  visibleKeys={visibleKeys}
                  expanded={expandedRows}
                  showAdvanced={showAdvanced}
                  showPack={showPack}
                  showDiscount={showDiscount}
                  priceInclusive={priceMode === 'INCLUSIVE'}
                  productChoiceRequired={reviewV2}
                  focusKey={focusKey}
                  onActiveRow={setActiveKey}
                  onToggleExpand={(key, open) =>
                    setExpandedRows((prev) => {
                      const next = new Set(prev);
                      if (open) next.add(key);
                      else next.delete(key);
                      return next;
                    })
                  }
                  onChange={updateLine}
                  onDelete={deleteRow}
                />
                <Button size="small" onClick={addRow} sx={{ alignSelf: 'flex-start' }}>
                  {t('billUpload.addRow')}
                </Button>
              </>
            )}

            <BillTotalsPanel
              totals={preview.totals}
              updating={hasUnsaved || saveState === 'saving'}
              priceMode={priceMode}
              additionalCharges={additionalCharges}
              invoiceDiscount={invoiceDiscount}
              printedTotal={printedTotal}
              onPriceMode={touchHeader(setPriceMode)}
              onAdditionalCharges={touchHeader(setAdditionalCharges)}
              onInvoiceDiscount={touchHeader(setInvoiceDiscount)}
              onPrintedTotal={touchHeader(setPrintedTotal)}
            />

            <Box>
              {confirmsNeeded ? (
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  {t('billUpload.confirmBeforeTitle')}
                </Typography>
              ) : null}
              {newProductCount > 0 ? (
                <Alert severity="info" sx={{ mb: 2 }}>
                  <Typography variant="body2">{t('billUpload.newProductsSummary', { count: newProductCount })}</Typography>
                  {reviewV2 ? (
                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={confirmNewProducts}
                          onChange={(e) => touchHeader(setConfirmNewProducts)(e.target.checked)}
                        />
                      }
                      label={t('billUpload.confirmNewProducts')}
                    />
                  ) : null}
                </Alert>
              ) : null}
              {allZeroRate ? (
                <Box sx={{ mb: 2, p: 1.5, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={confirmNonGst}
                        onChange={(e) => touchHeader(setConfirmNonGst)(e.target.checked)}
                        color="primary"
                      />
                    }
                    label={
                      <Box>
                        <Typography variant="body2" fontWeight={600}>
                          {t('sweep2.bookNonGst')}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          {t('billUpload.nonGstHelp')}
                        </Typography>
                      </Box>
                    }
                  />
                </Box>
              ) : null}
              {needsDuplicateConfirm ? (
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={confirmDuplicate}
                      onChange={(e) => touchHeader(setConfirmDuplicate)(e.target.checked)}
                    />
                  }
                  label={t('billUpload.notDuplicate')}
                />
              ) : null}
              {report?.headerErrors.some((e) => e.code === 'DUPLICATE_FILE') ? (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  {t('billUpload.duplicateFile')}
                </Alert>
              ) : null}
              {lowConfidence ? (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  <Typography variant="body2">
                    {t('billUpload.lowConfidence', { confidence: extractionConfidence.toFixed(2) })}
                  </Typography>
                  <Typography variant="caption" display="block">
                    {t('billUpload.lineReviewHint')}
                  </Typography>
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={lowConfidenceAccepted}
                        onChange={(e) => touchHeader(setLowConfidenceAccepted)(e.target.checked)}
                      />
                    }
                    label={t('billUpload.acceptReviewed')}
                  />
                </Alert>
              ) : null}
              {blockingHeaderErrors.length > 0 ? (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <strong>{t('billUpload.headerProblems')}:</strong>
                  <ul style={{ margin: '4px 0 0', paddingLeft: '1.2em' }}>
                    {blockingHeaderErrors.map((e, i) => (
                      <li key={i}>{e.message}</li>
                    ))}
                  </ul>
                </Alert>
              ) : null}
              {report?.ok ? (
                <Alert severity="success" sx={{ mb: 2 }}>
                  {t('billUpload.checkOk')}{' '}
                  {t('billUpload.checkSummary', {
                    included: report.summary.included,
                    excluded: report.summary.excluded,
                    newProducts: report.summary.newProducts,
                  })}
                </Alert>
              ) : null}
              {invalidIncludedCount > 0 ? (
                <Alert
                  severity="error"
                  sx={{ mb: 2 }}
                  action={
                    <Button
                      color="inherit"
                      size="small"
                      onClick={() => {
                        setRowFilter('problems');
                        const first = problemKeys[0];
                        if (first) {
                          setExpandedRows((prev) => new Set(prev).add(first));
                          setFocusKey(first);
                        }
                      }}
                    >
                      {t('billUpload.goToFirst')}
                    </Button>
                  }
                >
                  {t('billUpload.rowsNeedFixing', { count: invalidIncludedCount })}
                </Alert>
              ) : null}
              <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
                <Button variant="contained" color="secondary" disabled={commitBlocked} onClick={() => commitMutation.mutate()}>
                  {t(isSales ? 'billUpload.commitDraftSales' : 'billUpload.commitDraft')}
                </Button>
                <Button
                  variant="outlined"
                  disabled={checkMutation.isPending || commitMutation.isPending}
                  onClick={() => checkMutation.mutate()}
                >
                  {t('billUpload.checkBeforeCreate')}
                </Button>
                {saveLabel ? (
                  <Typography variant="caption" color={saveState === 'failed' ? 'error' : 'text.secondary'}>
                    {saveLabel}
                    {saveState === 'failed' ? (
                      <Button size="small" onClick={() => void startSave()}>
                        {t('billUpload.retrySave')}
                      </Button>
                    ) : null}
                  </Typography>
                ) : null}
                <Button
                  size="small"
                  color="inherit"
                  disabled={cancelMutation.isPending}
                  onClick={async () => {
                    // Discarding throws away every correction made here, so ask first.
                    if (await confirmAction(`${t('billUpload.discardTitle')}\n\n${t('billUpload.discardBody')}`)) {
                      cancelMutation.mutate();
                    }
                  }}
                >
                  {t('billUpload.discardUpload')}
                </Button>
              </Stack>
              {commitBlocked && blockerReason ? (
                <Typography variant="body2" color="warning.main" sx={{ mt: 1 }} role="status">
                  {t('billUpload.blockedBecause', { reason: blockerReason })}
                </Typography>
              ) : null}
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {t(isSales ? 'billUpload.commitDraftHintSales' : 'billUpload.commitDraftHint')}
              </Typography>
            </Box>
          </Stack>
        </Paper>
      </Box>

      {narrow ? (
        <Drawer anchor="bottom" open={showSource} onClose={() => setShowSource(false)}>
          <Box sx={{ p: 1, maxHeight: '75vh', overflow: 'auto' }}>
            <SourceBillViewer key={jobId} jobId={jobId} highlight={activeBox} />
          </Box>
        </Drawer>
      ) : null}
      <Snackbar
        open={undoOpen}
        autoHideDuration={6000}
        onClose={() => setUndoOpen(false)}
        message={t('billUpload.rowDeleted')}
        action={
          <Button color="secondary" size="small" onClick={undoDelete}>
            {t('billUpload.undo')}
          </Button>
        }
      />
    </>
  );
}
