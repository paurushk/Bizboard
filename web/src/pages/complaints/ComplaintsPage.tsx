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
  complaintDocument,
  complaintReport,
  createComplaint,
  deleteComplaintAttachment,
  getComplaint,
  listComplaintAttachments,
  listComplaintsPage,
  transitionComplaint,
  updateComplaint,
  uploadComplaintAttachment,
} from '@/api/growth';
import { listSalesInvoicesPage, getSalesInvoice } from '@/api/resources';
import { PageTitle } from '@/contextHelp';
import { isComplaintsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { AttachmentEditor, CustomerField, ProductField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

const CATEGORIES = ['DAMAGED', 'WRONG_DELIVERY', 'QUALITY', 'OTHER'] as const;
const NEXT: Record<string, string[]> = {
  OPEN: ['INSPECTING'],
  INSPECTING: ['APPROVED', 'REJECTED'],
  APPROVED: ['RESOLVED'],
  REJECTED: [],
  RESOLVED: [],
};
const DOC_OK = new Set(['INSPECTING', 'APPROVED']);

export function ComplaintsPage() {
  if (!isComplaintsEnabled()) {
    return <PageShell title={t('nav.complaints')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <ComplaintsInner />;
}

function ComplaintsInner() {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [category, setCategory] = useState('OTHER');
  const [description, setDescription] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['complaints', statusFilter, categoryFilter],
    queryFn: () => listComplaintsPage({
      pageSize: 50,
      status: statusFilter || undefined,
      category: categoryFilter || undefined,
    }),
  });
  const report = useQuery({ queryKey: ['complaints-report'], queryFn: complaintReport });
  const create = useMutation({
    mutationFn: () => createComplaint({ customer: customer!.id, category, description }),
    onSuccess: () => {
      setDescription('');
      setError('');
      void qc.invalidateQueries({ queryKey: ['complaints'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.complaints')}</PageTitle>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField select size="small" label={t('growth.category')} value={category} onChange={(e) => setCategory(e.target.value)} sx={{ minWidth: 160 }}>
          {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
        </TextField>
        <TextField size="small" label={t('growth.description')} value={description} onChange={(e) => setDescription(e.target.value)} />
        <Button variant="contained" disabled={!customer || !description.trim() || create.isPending} onClick={() => create.mutate()}>{t('growth.create')}</Button>
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
      {selectedId ? <ComplaintDetail key={selectedId} id={selectedId} onError={setError} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2">{t('growth.report')}</Typography>
        <Typography variant="body2">
          {t('growth.resolved')}: {report.data?.resolved ?? 0} · {t('growth.withDocument')}: {report.data?.resolvedWithDocument ?? 0} · {t('growth.withoutDocument')}: {report.data?.resolvedWithoutDocument ?? 0}
        </Typography>
        <Typography variant="body2">{t('growth.average')}: {report.data?.averageResolutionSeconds ?? '—'}</Typography>
        {(report.data?.byCategory ?? []).map((row) => (
          <Typography key={row.category} variant="caption" display="block">{row.category}: {row.count}</Typography>
        ))}
      </Paper>
    </Stack>
  );
}

function ComplaintDetail({ id, onError }: { id: number; onError: (message: string) => void }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState<string | null>(null);
  const [invoiceId, setInvoiceId] = useState('');
  const [product, setProduct] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [sourceItem, setSourceItem] = useState('');
  const detail = useQuery({ queryKey: ['complaint', id], queryFn: () => getComplaint(id) });
  const files = useQuery({ queryKey: ['complaint-files', id], queryFn: () => listComplaintAttachments(id) });
  const invoices = useQuery({
    queryKey: ['complaint-invoices', detail.data?.customer],
    queryFn: () => listSalesInvoicesPage({ customer: detail.data!.customer, pageSize: 20 }),
    enabled: Boolean(detail.data?.customer),
  });
  const invoiceDetail = useQuery({
    queryKey: ['complaint-invoice', detail.data?.sourceInvoice],
    queryFn: () => getSalesInvoice(detail.data!.sourceInvoice as number),
    enabled: Boolean(detail.data?.sourceInvoice),
  });
  const row = detail.data;
  const invoiceLines = (invoiceDetail.data?.items ?? []) as { id?: number; product: number; productName?: string; unitPrice?: string | number }[];
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['complaint', id] });
    void qc.invalidateQueries({ queryKey: ['complaints'] });
    void qc.invalidateQueries({ queryKey: ['complaints-report'] });
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
  const returnItems = line?.id != null
    ? [{ product: line.product, quantity, unit_price: linePrice }]
    : [];
  const creditItems = line?.id != null
    ? [{ product: line.product, quantity, unit_price: linePrice, source_item: line.id }]
    : [];
  const orderItems = product ? [{ product: product.id, quantity, unit_price: price.trim() || '0' }] : [];
  const quantityValid = Number(quantity) > 0;
  const noteValue = notes ?? row.inspectionNotes ?? '';
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2">{row.number} · {row.status}</Typography>
      <Typography variant="body2">{row.description}</Typography>
      <TextField size="small" fullWidth multiline minRows={2} sx={{ mt: 1 }} label={t('growth.inspectionNotes')} value={noteValue} onChange={(e) => setNotes(e.target.value)} />
      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        {(NEXT[row.status] ?? []).map((status) => (
          <Button key={status} size="small" variant="outlined" onClick={() => run.mutate(() => transitionComplaint(id, { status, inspection_notes: noteValue }))}>
            {t('growth.moveTo')} {status}
          </Button>
        ))}
      </Stack>
      <TextField select size="small" sx={{ mt: 1, minWidth: 220 }} label={t('growth.sourceInvoice')} value={invoiceId || (row.sourceInvoice ? String(row.sourceInvoice) : '')} onChange={(e) => {
        const next = e.target.value;
        setInvoiceId(next);
        setSourceItem('');
        void updateComplaint(id, { source_invoice: next ? Number(next) : null }).then(refresh).catch((err) => onError(getErrorMessage(err)));
      }}>
        <MenuItem value="">{t('growth.none')}</MenuItem>
        {(invoices.data?.results ?? []).map((invoice) => (
          <MenuItem key={invoice.id} value={String(invoice.id)}>{invoice.number || invoice.id}</MenuItem>
        ))}
        {row.sourceInvoice && !(invoices.data?.results ?? []).some((invoice) => invoice.id === row.sourceInvoice) ? (
          <MenuItem value={String(row.sourceInvoice)}>#{row.sourceInvoice}</MenuItem>
        ) : null}
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
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }} alignItems={{ md: 'center' }}>
        <ProductField value={product} onChange={setProduct} />
        <TextField size="small" label={t('growth.quantity')} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <TextField size="small" label={t('growth.unitPrice')} value={price} onChange={(e) => setPrice(e.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
        <Button size="small" disabled={!canDoc || !row.sourceInvoice || !line || !quantityValid} onClick={() => run.mutate(() => complaintDocument(id, 'create-return', returnItems))}>{t('growth.createReturn')}</Button>
        <Button size="small" disabled={!canDoc || !row.sourceInvoice || !line || !quantityValid} onClick={() => run.mutate(() => complaintDocument(id, 'create-credit-note', creditItems))}>{t('growth.createCreditNote')}</Button>
        <Button size="small" disabled={!canDoc || !product || !quantityValid} onClick={() => run.mutate(() => complaintDocument(id, 'create-replacement-order', orderItems))}>{t('growth.createReplacement')}</Button>
      </Stack>
      <Typography variant="caption" display="block" sx={{ mt: 1 }}>
        {t('growth.documents')}: {row.salesReturn ?? '—'} / {row.salesCreditNote ?? '—'} / {row.replacementOrder ?? '—'}
      </Typography>
      <AttachmentEditor
        rows={files.data ?? []}
        onUpload={(file) => run.mutate(async () => {
          await uploadComplaintAttachment(id, file);
          await qc.invalidateQueries({ queryKey: ['complaint-files', id] });
        })}
        onDelete={(attachmentId) => run.mutate(async () => {
          await deleteComplaintAttachment(id, attachmentId);
          await qc.invalidateQueries({ queryKey: ['complaint-files', id] });
        })}
      />
    </Paper>
  );
}
