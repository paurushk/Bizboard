import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  createSupplierComplaint,
  createSupplierDebitNote,
  deleteSupplierComplaintAttachment,
  getSupplierComplaint,
  listSupplierComplaintAttachments,
  listSupplierComplaintsPage,
  supplierComplaintReport,
  transitionSupplierComplaint,
  updateSupplierComplaint,
  uploadSupplierComplaintAttachment,
} from '@/api/growth';
import { getPurchase, listPurchasesPage } from '@/api/legacy/purchases';
import { PageTitle } from '@/contextHelp';
import { isComplaintsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { AttachmentEditor, SupplierField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Supplier } from '@/types/domain';

const CATEGORIES = ['DAMAGED', 'WRONG_DELIVERY', 'QUALITY', 'OTHER'] as const;
const NEXT: Record<string, string[]> = {
  OPEN: ['INSPECTING'],
  INSPECTING: ['APPROVED', 'REJECTED'],
  APPROVED: ['RESOLVED'],
  REJECTED: [],
  RESOLVED: [],
};
const DOC_OK = new Set(['INSPECTING', 'APPROVED']);

export function SupplierComplaintsPage() {
  if (!isComplaintsEnabled()) {
    return <PageShell title={t('nav.supplierComplaints')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <SupplierComplaintsInner />;
}

function SupplierComplaintsInner() {
  const qc = useQueryClient();
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [category, setCategory] = useState('OTHER');
  const [description, setDescription] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['supplier-complaints', statusFilter, categoryFilter],
    queryFn: () => listSupplierComplaintsPage({
      pageSize: 50,
      status: statusFilter || undefined,
      category: categoryFilter || undefined,
    }),
  });
  const report = useQuery({ queryKey: ['supplier-complaints-report'], queryFn: supplierComplaintReport });
  const create = useMutation({
    mutationFn: () => createSupplierComplaint({ supplier: supplier!.id, category, description }),
    onSuccess: () => {
      setDescription('');
      setError('');
      void qc.invalidateQueries({ queryKey: ['supplier-complaints'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.supplierComplaints')}</PageTitle>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <SupplierField value={supplier} onChange={setSupplier} />
        <TextField select size="small" label={t('growth.category')} value={category} onChange={(e) => setCategory(e.target.value)} sx={{ minWidth: 160 }}>
          {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
        </TextField>
        <TextField size="small" label={t('growth.description')} value={description} onChange={(e) => setDescription(e.target.value)} />
        <Button variant="contained" disabled={!supplier || !description.trim() || create.isPending} onClick={() => create.mutate()}>{t('growth.create')}</Button>
      </Stack>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <TextField select size="small" label={t('growth.status')} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {Object.keys(NEXT).map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('growth.category')} value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
        </TextField>
      </Stack>
      {error ? <Typography color="error">{error}</Typography> : null}
      {(list.data?.results ?? []).map((row) => (
        <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction="row" justifyContent="space-between">
            <Typography>{row.number} · {row.category} · {row.status}</Typography>
            <Button size="small" onClick={() => setSelectedId(row.id)}>{t('growth.detail')}</Button>
          </Stack>
        </Paper>
      ))}
      {selectedId ? <SupplierComplaintDetail key={selectedId} id={selectedId} onError={setError} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2">{t('growth.report')}</Typography>
        <Typography variant="body2">
          {t('growth.resolved')}: {report.data?.resolved ?? 0} · {t('growth.withDocument')}: {report.data?.resolvedWithDocument ?? 0} · {t('growth.withoutDocument')}: {report.data?.resolvedWithoutDocument ?? 0}
        </Typography>
        <Typography variant="body2">{t('growth.average')}: {report.data?.averageResolutionSeconds ?? '—'}</Typography>
      </Paper>
    </Stack>
  );
}

function SupplierComplaintDetail({ id, onError }: { id: number; onError: (message: string) => void }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState<string | null>(null);
  const [invoiceId, setInvoiceId] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [sourceItem, setSourceItem] = useState('');
  const detail = useQuery({ queryKey: ['supplier-complaint', id], queryFn: () => getSupplierComplaint(id) });
  const files = useQuery({ queryKey: ['supplier-complaint-files', id], queryFn: () => listSupplierComplaintAttachments(id) });
  const invoices = useQuery({
    queryKey: ['supplier-complaint-bills', detail.data?.supplier],
    queryFn: () => listPurchasesPage({ supplier: detail.data!.supplier, pageSize: 20 }),
    enabled: Boolean(detail.data?.supplier),
  });
  const invoiceDetail = useQuery({
    queryKey: ['supplier-complaint-bill', detail.data?.sourceInvoice],
    queryFn: () => getPurchase(detail.data!.sourceInvoice as number),
    enabled: Boolean(detail.data?.sourceInvoice),
  });
  const row = detail.data;
  const invoiceLines = invoiceDetail.data?.items ?? [];
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['supplier-complaint', id] });
    void qc.invalidateQueries({ queryKey: ['supplier-complaints'] });
    void qc.invalidateQueries({ queryKey: ['supplier-complaints-report'] });
  };
  const run = useMutation({
    mutationFn: async (work: () => Promise<unknown>) => work(),
    onSuccess: () => { onError(''); refresh(); },
    onError: (err) => onError(getErrorMessage(err)),
  });
  if (!row) return null;
  const canDoc = DOC_OK.has(row.status);
  const line = invoiceLines.find((item) => item.id != null && String(item.id) === sourceItem);
  const linePrice = price.trim() || String(line?.unitPrice ?? '0');
  const debitItems = line?.id != null
    ? [{ product: line.product, quantity, unit_price: linePrice, source_item: line.id }]
    : [];
  const quantityValid = Number(quantity) > 0;
  const noteValue = notes ?? row.inspectionNotes ?? '';
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2">{row.number} · {row.status}</Typography>
      <Typography variant="body2">{row.description}</Typography>
      <TextField size="small" fullWidth multiline minRows={2} sx={{ mt: 1 }} label={t('growth.inspectionNotes')} value={noteValue} onChange={(e) => setNotes(e.target.value)} />
      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        {(NEXT[row.status] ?? []).map((status) => (
          <Button key={status} size="small" variant="outlined" onClick={() => run.mutate(() => transitionSupplierComplaint(id, { status, inspection_notes: noteValue }))}>
            {t('growth.moveTo')} {status}
          </Button>
        ))}
      </Stack>
      <TextField select size="small" sx={{ mt: 1, minWidth: 220 }} label={t('growth.sourceInvoice')} value={invoiceId || (row.sourceInvoice ? String(row.sourceInvoice) : '')} onChange={(e) => {
        const next = e.target.value;
        setInvoiceId(next);
        setSourceItem('');
        void updateSupplierComplaint(id, { source_invoice: next ? Number(next) : null }).then(refresh).catch((err) => onError(getErrorMessage(err)));
      }}>
        <MenuItem value="">{t('growth.none')}</MenuItem>
        {(invoices.data?.results ?? []).map((invoice) => (
          <MenuItem key={invoice.id} value={String(invoice.id)}>{invoice.number || invoice.id}</MenuItem>
        ))}
      </TextField>
      {invoiceLines.length ? (
        <TextField select size="small" sx={{ mt: 1, minWidth: 220, display: 'block' }} label={t('growth.sourceLine')} value={sourceItem} onChange={(e) => setSourceItem(e.target.value)}>
          <MenuItem value="">{t('growth.none')}</MenuItem>
          {invoiceLines.map((item) => (
            <MenuItem key={item.id} value={String(item.id)}>
              {item.productName ? `${item.productName}` : `#${item.product}`} · {item.unitPrice ?? ''}
            </MenuItem>
          ))}
        </TextField>
      ) : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}>
        <TextField size="small" label={t('growth.quantity')} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <TextField size="small" label={t('growth.unitPrice')} value={price} onChange={(e) => setPrice(e.target.value)} />
      </Stack>
      <Button size="small" sx={{ mt: 1 }} disabled={!canDoc || !row.sourceInvoice || !line || !quantityValid} onClick={() => run.mutate(() => createSupplierDebitNote(id, debitItems))}>
        {t('growth.createDebitNote')}
      </Button>
      <Typography variant="caption" display="block" sx={{ mt: 1 }}>
        {t('growth.createDebitNote')}: {row.purchaseDebitNote ?? '—'}
      </Typography>
      <AttachmentEditor
        rows={files.data ?? []}
        onUpload={(file) => run.mutate(async () => {
          await uploadSupplierComplaintAttachment(id, file);
          await qc.invalidateQueries({ queryKey: ['supplier-complaint-files', id] });
        })}
        onDelete={(attachmentId) => run.mutate(async () => {
          await deleteSupplierComplaintAttachment(id, attachmentId);
          await qc.invalidateQueries({ queryKey: ['supplier-complaint-files', id] });
        })}
      />
    </Paper>
  );
}
