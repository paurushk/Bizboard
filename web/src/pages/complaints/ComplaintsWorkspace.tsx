/** Customer and supplier complaints share one workspace; `kind` picks the party and the remedy documents. */
import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Link from '@mui/material/Link';
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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { complaints, returnableLines, type Complaint, type ComplaintDocument, type ComplaintKind } from '@/api/care';
import {
  completeSalesCreditNote,
  getCustomer,
  getPurchase,
  getPurchaseDebitNote,
  getSalesCreditNote,
  getSalesInvoice,
  getSalesOrder,
  getSalesReturn,
  listPurchasesPage,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, ListSkeleton } from '@/components/PageState';
import { isComplaintsEnabled } from '@/config/features';
import { t } from '@/i18n';
import { AttachmentPanel } from '@/care/attachments';
import { ageSeconds, formatSpan, formatStamp, plainNumber } from '@/care/format';
import {
  ActivityTimeline,
  CareHeader,
  CareTable,
  CustomerLink,
  EntityPicker,
  Field,
  LinkedRecords,
  MasterDetail,
  MemberPicker,
  Pager,
  SearchField,
  StatusPill,
  type CareColumn,
  VisuallyHidden,
} from '@/care/kit';
import { canChangeCare, useListPath, useNotice, useUrlFilters } from '@/care/hooks';
import { CatalogPicker, InvoicePicker } from '@/care/pickers';
import { completeWithConfirms } from '@/utils/completeWithConfirms';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { CustomerField, SupplierField } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product, PurchaseInvoice, SalesInvoice, Supplier } from '@/types/domain';

const CATEGORIES = ['DAMAGED', 'WRONG_DELIVERY', 'QUALITY', 'OTHER'] as const;
const STATUSES = ['OPEN', 'INSPECTING', 'APPROVED', 'REJECTED', 'RESOLVED'] as const;
const NEXT: Record<string, string[]> = {
  OPEN: ['INSPECTING'],
  INSPECTING: ['APPROVED', 'REJECTED'],
  APPROVED: ['RESOLVED'],
  REJECTED: [],
  RESOLVED: [],
};
const PAGE_SIZE = 20;
const CLOSED = new Set(['RESOLVED', 'REJECTED']);

type Cfg = {
  kind: ComplaintKind;
  base: string;
  title: string;
  entity: 'Complaint' | 'SupplierComplaint';
  documents: string[];
  purchases: boolean;
};

const CUSTOMER: Cfg = {
  kind: 'customer', base: '/complaints', title: 'nav.complaints', entity: 'Complaint',
  documents: ['salesReturn', 'salesCreditNote', 'replacementOrder'], purchases: false,
};
const SUPPLIER: Cfg = {
  kind: 'supplier', base: '/complaints/suppliers', title: 'nav.supplierComplaints', entity: 'SupplierComplaint',
  documents: ['purchaseDebitNote'], purchases: true,
};

export function ComplaintsWorkspacePage({ supplier }: { supplier: boolean }) {
  const cfg = supplier ? SUPPLIER : CUSTOMER;
  if (!isComplaintsEnabled()) {
    return <PageShell title={t(cfg.title)}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <Workspace cfg={cfg} />;
}

function partyName(row: Complaint, cfg: Cfg) {
  return (cfg.purchases ? row.supplierName : row.customerName) ?? '';
}

function Workspace({ cfg }: { cfg: Cfg }) {
  const { id } = useParams();
  const selectedId = id ? Number(id) : null;
  const { user } = useAuth();
  const canChange = canChangeCare(user, cfg.purchases ? 'purchases' : 'sales');
  const api = complaints(cfg.kind);
  const listPath = useListPath(cfg.base);
  const [searchParams, setSearchParams] = useSearchParams();
  const { values, set } = useUrlFilters({ q: '', status: '', category: '', assigned: '', mine: '', from: '', to: '', page: '1' });
  const [reportOpen, setReportOpen] = useState(false);
  const page = Math.max(1, Number(values.page) || 1);
  const filters = {
    q: values.q || undefined,
    status: values.status || undefined,
    category: values.category || undefined,
    assigned_to: values.assigned || undefined,
    mine: values.mine ? 1 : undefined,
    created_from: values.from || undefined,
    created_to: values.to || undefined,
  };
  const list = useQuery({
    queryKey: ['complaints', cfg.kind, 'list', filters, page],
    queryFn: () => api.list({ ...filters, page, pageSize: PAGE_SIZE }),
  });
  const rows = list.data?.results ?? [];
  const createOpen = searchParams.get('new') === '1';
  const closeCreate = () =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      ['new', 'customer', 'ticket', 'invoice'].forEach((key) => next.delete(key));
      return next;
    }, { replace: true });

  const columns: CareColumn<Complaint>[] = [
    {
      key: 'number', header: t('care.complaints.col.complaint'), primary: true,
      render: (row) => `${row.number} · ${row.description.slice(0, 60)}${row.description.length > 60 ? '…' : ''}`,
    },
    { key: 'party', header: cfg.purchases ? t('growth.supplier') : t('growth.customer'), render: (row) => partyName(row, cfg) },
    { key: 'category', header: t('growth.category'), render: (row) => enumLabel('complaintCategory', row.category) },
    { key: 'status', header: t('growth.status'), render: (row) => <StatusPill group="complaintStatus" value={row.status} /> },
    { key: 'invoice', header: cfg.purchases ? t('care.complaints.bill') : t('growth.sourceInvoice'), render: (row) => row.sourceInvoiceNumber },
    { key: 'assignee', header: t('growth.assignee'), render: (row) => row.assigneeName || t('growth.unassigned') },
    { key: 'age', header: t('care.tickets.col.age'), render: (row) => formatSpan(ageSeconds(row.createdAt)) },
  ];

  const listNode = (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <SearchField value={values.q} onChange={(q) => set({ q })} />
        <TextField select size="small" label={t('growth.status')} value={values.status} onChange={(e) => set({ status: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {STATUSES.map((value) => <MenuItem key={value} value={value}>{enumLabel('complaintStatus', value)}</MenuItem>)}
        </TextField>
        <TextField select size="small" label={t('growth.category')} value={values.category} onChange={(e) => set({ category: e.target.value })} sx={{ minWidth: 160 }}>
          <MenuItem value="">{t('growth.all')}</MenuItem>
          {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('complaintCategory', value)}</MenuItem>)}
        </TextField>
        <MemberPicker label={t('growth.assignee')} value={values.assigned ? Number(values.assigned) : null} onChange={(m) => set({ assigned: m ? String(m) : '' })} minWidth={180} />
        <TextField size="small" type="date" label={t('care.complaints.from')} value={values.from} onChange={(e) => set({ from: e.target.value })} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label={t('care.complaints.to')} value={values.to} onChange={(e) => set({ to: e.target.value })} InputLabelProps={{ shrink: true }} />
        <FormControlLabel control={<Checkbox checked={Boolean(values.mine)} onChange={(e) => set({ mine: e.target.checked ? '1' : '' })} />} label={t('growth.mine')} />
      </Stack>
      {list.isLoading ? <ListSkeleton rows={6} /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && rows.length === 0 ? (
        <EmptyState
          description={t('cog.emptyComplaints')}
          action={canChange ? <Button variant="contained" onClick={() => setSearchParams({ new: '1' })}>{t('growth.newComplaint')}</Button> : undefined}
        />
      ) : null}
      {rows.length > 0 ? (
        <CareTable
          caption={t(cfg.title)}
          columns={selectedId ? columns.filter((c) => ['number', 'status', 'party'].includes(c.key)) : columns}
          rows={rows}
          rowKey={(row) => row.id}
          rowHref={(row) => listPath(`/${row.id}`)}
          selectedId={selectedId}
        />
      ) : null}
      <Pager page={page} count={list.data?.count ?? 0} pageSize={PAGE_SIZE} onPage={(next) => set({ page: String(next) })} />
    </Stack>
  );

  return (
    <Stack spacing={2}>
      <CareHeader
        title={t(cfg.title)}
        subtitle={cfg.purchases ? t('care.complaints.subtitleSupplier') : t('care.complaints.subtitle')}
        actions={
          <>
            <Button variant="outlined" onClick={() => setReportOpen((open) => !open)} aria-expanded={reportOpen}>
              {t('growth.report')}
            </Button>
            {canChange ? <Button variant="contained" onClick={() => setSearchParams({ new: '1' })}>{t('growth.newComplaint')}</Button> : null}
          </>
        }
      />
      {reportOpen ? <ReportPanel cfg={cfg} filters={filters} /> : null}
      <MasterDetail
        list={listNode}
        detail={selectedId ? <ComplaintDetail key={selectedId} cfg={cfg} id={selectedId} canChange={canChange} isOwner={user?.role === 'OWNER'} backTo={listPath()} /> : null}
        hasSelection={selectedId != null}
        backTo={listPath()}
        detailLabel={t('care.complaints.detail')}
      />
      <NewComplaintDialog cfg={cfg} open={createOpen && canChange} onClose={closeCreate} prefill={searchParams} />
    </Stack>
  );
}

function ReportPanel({ cfg, filters }: { cfg: Cfg; filters: Record<string, string | number | undefined> }) {
  const report = useQuery({
    queryKey: ['complaints', cfg.kind, 'report', filters],
    queryFn: () => complaints(cfg.kind).report(filters),
  });
  const data = report.data;
  return (
    <Paper variant="outlined" sx={{ p: 2 }} component="section" aria-label={t('growth.report')}>
      {report.isError ? <Typography color="error">{getErrorMessage(report.error)}</Typography> : null}
      {data ? (
        <Stack spacing={1}>
          <Typography variant="body2">
            {t('growth.resolved')}: {data.resolved} · {t('growth.withDocument')}: {data.resolvedWithDocument} · {t('growth.withoutDocument')}: {data.resolvedWithoutDocument}
          </Typography>
          <Typography variant="body2">{t('growth.average')}: {formatSpan(data.averageResolutionSeconds) || '—'}</Typography>
          <Typography variant="caption" color="text.secondary">{t('care.complaints.ageingTitle')}</Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            {data.ageing.map((bucket) => <Typography key={bucket.bucket} variant="body2">{bucket.bucket}: {bucket.count}</Typography>)}
          </Stack>
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
            {data.byCategory.map((row) => (
              <Typography key={row.category} variant="caption">{enumLabel('complaintCategory', row.category)}: {row.count}</Typography>
            ))}
          </Stack>
        </Stack>
      ) : null}
    </Paper>
  );
}

function NewComplaintDialog({
  cfg,
  open,
  onClose,
  prefill,
}: {
  cfg: Cfg;
  open: boolean;
  onClose: () => void;
  prefill: URLSearchParams;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const listPath = useListPath(cfg.base);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [category, setCategory] = useState('OTHER');
  const [description, setDescription] = useState('');
  const [invoice, setInvoice] = useState<SalesInvoice | null>(null);
  const [bill, setBill] = useState<PurchaseInvoice | null>(null);
  const [assignee, setAssignee] = useState<number | null>(null);
  const [error, setError] = useState('');
  // A link from a ticket opens this dialog with the customer, invoice and ticket already named.
  const prefillCustomer = Number(prefill.get('customer')) || null;
  const prefillInvoice = Number(prefill.get('invoice')) || null;
  const prefillTicket = Number(prefill.get('ticket')) || null;
  useQuery({
    queryKey: ['care-prefill-customer', prefillCustomer],
    enabled: open && !cfg.purchases && prefillCustomer != null && customer == null,
    queryFn: async () => {
      const row = await getCustomer(prefillCustomer!);
      setCustomer(row);
      return row;
    },
  });
  useQuery({
    queryKey: ['care-prefill-invoice', prefillInvoice],
    enabled: open && !cfg.purchases && prefillInvoice != null && invoice == null,
    queryFn: async () => {
      const row = await getSalesInvoice(prefillInvoice!);
      setInvoice(row);
      return row;
    },
  });
  const create = useMutation({
    mutationFn: () =>
      complaints(cfg.kind).create({
        ...(cfg.purchases ? { supplier: supplier!.id } : { customer: customer!.id, ticket: prefillTicket }),
        category,
        description: description.trim(),
        source_invoice: (cfg.purchases ? bill?.id : invoice?.id) ?? null,
        assigned_to: assignee,
      }),
    onSuccess: (row) => {
      void qc.invalidateQueries({ queryKey: ['complaints'] });
      setDescription(''); setInvoice(null); setBill(null); setError('');
      onClose();
      navigate(listPath(`/${row.id}`));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const party = cfg.purchases ? supplier : customer;
  return (
    <CreateDialog
      open={open}
      onClose={onClose}
      title={t('growth.newComplaint')}
      submitLabel={t('growth.logComplaint')}
      submitDisabled={!party || !description.trim() || create.isPending}
      dirty={Boolean(description.trim() || party)}
      onSubmit={() => create.mutate()}
    >
      {cfg.purchases ? (
        <SupplierField value={supplier} onChange={(next) => { setSupplier(next); setBill(null); }} />
      ) : (
        <CustomerField value={customer} onChange={(next) => { setCustomer(next); setInvoice(null); }} />
      )}
      <TextField select size="small" label={t('growth.category')} value={category} onChange={(e) => setCategory(e.target.value)}>
        {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('complaintCategory', value)}</MenuItem>)}
      </TextField>
      <TextField size="small" required multiline minRows={3} label={t('growth.description')} value={description} onChange={(e) => setDescription(e.target.value)} />
      {cfg.purchases ? (
        <EntityPicker<PurchaseInvoice>
          label={t('care.complaints.bill')}
          value={bill}
          onChange={setBill}
          disabled={!supplier}
          queryKey={['bill', supplier?.id]}
          search={async (q) => (await listPurchasesPage({ supplier: supplier?.id, q: q || undefined, pageSize: 20 })).results}
          getLabel={(row) => `${row.number || `#${row.id}`}`}
        />
      ) : (
        <InvoicePicker customerId={customer?.id ?? null} value={invoice} onChange={setInvoice} helperText={t('care.complaints.invoiceHelp')} />
      )}
      <MemberPicker label={t('growth.assignee')} value={assignee} onChange={setAssignee} minWidth={0} />
      {error ? <Typography role="alert" color="error" variant="body2">{error}</Typography> : null}
    </CreateDialog>
  );
}

type Pending = null | { status: 'REJECTED' | 'RESOLVED' };

export function ComplaintDetail({
  cfg,
  id,
  canChange,
  isOwner,
  backTo,
}: {
  cfg: Cfg;
  id: number;
  canChange: boolean;
  isOwner: boolean;
  backTo: { pathname: string; search: string };
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const api = complaints(cfg.kind);
  const feedback = useNotice();
  const [notes, setNotes] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [edit, setEdit] = useState(false);
  const [editText, setEditText] = useState('');
  const [editCategory, setEditCategory] = useState('OTHER');
  const [confirmDelete, setConfirmDelete] = useState(false);
  const detail = useQuery({ queryKey: ['complaints', cfg.kind, 'detail', id], queryFn: () => api.get(id) });
  const row = detail.data;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['complaints'] });
    void qc.invalidateQueries({ queryKey: ['care-activity', cfg.entity, id] });
    void qc.invalidateQueries({ queryKey: ['care-links'] });
  };
  const run = useMutation({
    mutationFn: async (job: { work: () => Promise<unknown>; done: string }) => {
      await job.work();
      return job.done;
    },
    onSuccess: (done) => { feedback.ok(done); refresh(); },
    onError: (err) => feedback.fail(err),
  });
  if (detail.isLoading) return <ListSkeleton rows={4} />;
  if (detail.isError || !row) {
    return <ErrorState message={getErrorMessage(detail.error)} error={detail.error} onRetry={() => void detail.refetch()} />;
  }
  const closed = CLOSED.has(row.status);
  const open = row.status === 'OPEN' || row.status === 'INSPECTING';
  const docIds = cfg.documents.map((name) => (row as unknown as Record<string, number | null>)[name]).filter(Boolean);
  const hasDocument = docIds.length > 0;
  const noteValue = notes ?? row.inspectionNotes ?? '';
  const notesDirty = notes != null && notes !== (row.inspectionNotes ?? '');
  const partyId = cfg.purchases ? row.supplier : row.customer;
  const moveTo = (status: string) => {
    if (status === 'REJECTED' || status === 'RESOLVED') setPending({ status });
    else run.mutate({ work: () => api.transition(id, { status, inspection_notes: notesDirty ? noteValue : undefined }), done: t('care.complaints.movedTo', { status: enumLabel('complaintStatus', status) }) });
  };
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={2}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
          <Box>
            <Typography variant="h6" component="h2">{row.number}</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <StatusPill group="complaintStatus" value={row.status} />
              <Typography variant="body2">{enumLabel('complaintCategory', row.category)}</Typography>
            </Stack>
          </Box>
          {canChange && open ? (
            <Button size="small" onClick={() => { setEditText(row.description); setEditCategory(row.category); setEdit(true); }}>{t('common.edit')}</Button>
          ) : null}
        </Stack>
        {feedback.node}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
          <Field label={cfg.purchases ? t('growth.supplier') : t('growth.customer')}>
            {cfg.purchases ? partyName(row, cfg) : <CustomerLink id={partyId ?? 0} name={partyName(row, cfg)} />}
          </Field>
          <Field label={t('care.common.created')}>{formatStamp(row.createdAt)}</Field>
          {row.resolvedAt ? <Field label={t('care.complaints.resolvedAt')}>{formatStamp(row.resolvedAt)}</Field> : null}
          {row.ticket ? (
            <Field label={t('care.pick.ticket')}>
              <Link component={RouterLink} to={`/support/tickets/${row.ticket}`}>{row.ticketNumber}</Link>
            </Field>
          ) : null}
        </Stack>
        <Field label={t('growth.description')}><Box sx={{ whiteSpace: 'pre-wrap' }}>{row.description}</Box></Field>
        <MemberPicker
          label={t('growth.assignee')}
          value={row.assignedTo}
          disabled={!canChange || closed}
          onChange={(member) => run.mutate({ work: () => api.update(id, { assigned_to: member }, row.updatedAt), done: t('care.tickets.saved') })}
        />
        <Divider />
        <Box>
          <TextField
            fullWidth
            size="small"
            multiline
            minRows={2}
            label={t('growth.inspectionNotes')}
            value={noteValue}
            disabled={!canChange || closed}
            onChange={(e) => setNotes(e.target.value)}
            helperText={notesDirty ? t('care.complaints.notesUnsaved') : undefined}
          />
          {canChange && !closed ? (
            <Button
              size="small"
              sx={{ mt: 0.5 }}
              disabled={!notesDirty || run.isPending}
              onClick={() => run.mutate({ work: async () => { await api.saveNotes(id, noteValue); setNotes(null); }, done: t('care.complaints.notesSaved') })}
            >
              {t('care.complaints.saveNotes')}
            </Button>
          ) : null}
        </Box>
        {row.resolutionNote ? <Field label={t('care.complaints.resolutionNote')}>{row.resolutionNote}</Field> : null}
        {canChange ? (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {(NEXT[row.status] ?? []).map((status) => (
              <Button
                key={status}
                size="small"
                variant="outlined"
                color={status === 'REJECTED' ? 'error' : 'primary'}
                disabled={run.isPending}
                onClick={() => moveTo(status)}
              >
                {t('growth.moveTo')} {enumLabel('complaintStatus', status)}
              </Button>
            ))}
            {!cfg.purchases && !row.ticket ? (
              <Button size="small" disabled={run.isPending} onClick={() => run.mutate({ work: () => api.createTicket(id), done: t('care.complaints.ticketOpened') })}>
                {t('care.complaints.openTicket')}
              </Button>
            ) : null}
            {!cfg.purchases && !closed ? (
              <Button size="small" component={RouterLink} to={`/workshop/jobs/new?complaint=${row.id}&customer=${row.customer}`}>
                {t('care.complaints.createJob')}
              </Button>
            ) : null}
            {isOwner && !closed && !hasDocument ? (
              <Button size="small" color="error" onClick={() => setConfirmDelete(true)}>{t('common.delete')}</Button>
            ) : null}
          </Stack>
        ) : null}
        <Divider />
        <RemedySection cfg={cfg} row={row} canChange={canChange} onChanged={refresh} notice={feedback} />
        <Divider />
        <AttachmentPanel
          queryKey={['complaints', cfg.kind, 'files', id]}
          list={() => api.attachments.list(id)}
          upload={(file) => api.attachments.upload(id, file)}
          remove={(attachment) => api.attachments.remove(id, attachment)}
          canEdit={canChange}
          lockedReason={closed ? t('care.complaints.closedFiles') : undefined}
        />
        <Divider />
        <LinkedRecords entity={cfg.purchases ? 'supplier_complaint' : 'complaint'} id={id} />
        <ActivityTimeline entity={cfg.entity} id={id} fetcher={() => api.activity(id)} />
      </Stack>

      <CreateDialog
        open={edit}
        onClose={() => setEdit(false)}
        title={t('care.complaints.editTitle')}
        submitLabel={t('growth.save')}
        submitDisabled={!editText.trim()}
        onSubmit={() => {
          run.mutate({ work: () => api.update(id, { description: editText.trim(), category: editCategory }, row.updatedAt), done: t('care.tickets.saved') });
          setEdit(false);
        }}
      >
        <TextField select size="small" label={t('growth.category')} value={editCategory} onChange={(e) => setEditCategory(e.target.value)}>
          {CATEGORIES.map((value) => <MenuItem key={value} value={value}>{enumLabel('complaintCategory', value)}</MenuItem>)}
        </TextField>
        <TextField size="small" multiline minRows={4} label={t('growth.description')} value={editText} onChange={(e) => setEditText(e.target.value)} />
      </CreateDialog>

      <ConfirmDialog
        open={pending?.status === 'REJECTED'}
        title={t('care.complaints.rejectTitle', { number: row.number })}
        body={t('care.complaints.rejectBody')}
        confirmLabel={t('care.complaints.reject')}
        confirmColor="error"
        requireReason={{ label: t('care.complaints.rejectReason'), maxLength: 500 }}
        onClose={() => setPending(null)}
        onConfirm={(reason) => {
          setPending(null);
          run.mutate({ work: () => api.transition(id, { status: 'REJECTED', inspection_notes: reason }), done: t('care.complaints.rejected') });
        }}
      />
      {hasDocument ? (
        <ConfirmDialog
          open={pending?.status === 'RESOLVED'}
          title={t('care.complaints.resolveTitle', { number: row.number })}
          body={t('care.complaints.resolveBody')}
          confirmLabel={t('care.complaints.resolve')}
          onClose={() => setPending(null)}
          onConfirm={() => {
            setPending(null);
            run.mutate({ work: () => api.transition(id, { status: 'RESOLVED' }), done: t('care.complaints.resolved') });
          }}
        />
      ) : (
        <ConfirmDialog
          open={pending?.status === 'RESOLVED'}
          title={t('care.complaints.resolveTitle', { number: row.number })}
          body={t('care.complaints.resolveNoDocument')}
          confirmLabel={t('care.complaints.resolve')}
          requireReason={{ label: t('care.complaints.resolutionNote'), maxLength: 500 }}
          onClose={() => setPending(null)}
          onConfirm={(reason) => {
            setPending(null);
            run.mutate({ work: () => api.transition(id, { status: 'RESOLVED', resolution_note: reason }), done: t('care.complaints.resolved') });
          }}
        />
      )}
      <ConfirmDialog
        open={confirmDelete}
        title={t('care.complaints.deleteTitle', { number: row.number })}
        body={t('care.complaints.deleteBody')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          run.mutate({ work: async () => { await api.remove(id); navigate(backTo); }, done: t('care.complaints.deleted') });
        }}
      />
    </Paper>
  );
}

// ---- remedies -------------------------------------------------------------------------------------------------------------------

type PickRow = { key: number; product: number; name: string; sold: number; limit: number; price: string; quantity: string; picked: boolean };

function RemedySection({
  cfg,
  row,
  canChange,
  onChanged,
  notice,
}: {
  cfg: Cfg;
  row: Complaint;
  canChange: boolean;
  onChanged: () => void;
  notice: ReturnType<typeof useNotice>;
}) {
  const api = complaints(cfg.kind);
  const closed = CLOSED.has(row.status);
  const approved = row.status === 'APPROVED';
  const hasDocument = cfg.documents.some((name) => (row as unknown as Record<string, number | null>)[name]);
  const [order, setOrder] = useState<{ product: Product | null; quantity: string; price: string }[]>([{ product: null, quantity: '1', price: '' }]);
  // What the person ticked or typed, kept apart from the lines so a reload never loses it.
  const [edits, setEdits] = useState<Record<string, Partial<PickRow>>>({});
  const invoiceId = row.sourceInvoice;
  const lines = useQuery({
    queryKey: ['care-remedy-lines', cfg.kind, invoiceId],
    enabled: Boolean(invoiceId) && approved && canChange,
    queryFn: async (): Promise<PickRow[]> => {
      if (cfg.purchases) {
        const bill = await getPurchase(invoiceId!);
        return (bill.items ?? []).map((item) => ({
          key: item.id ?? item.product, product: item.product, name: item.productName ?? `#${item.product}`,
          sold: Number(item.quantity), limit: Number(item.quantity), price: String(item.unitPrice),
          quantity: '1', picked: false,
        }));
      }
      const [returnable, invoice] = await Promise.all([returnableLines(invoiceId!), getSalesInvoice(invoiceId!)]);
      const price = new Map((invoice.items ?? []).map((item) => [item.id ?? 0, String(item.unitPrice)]));
      return returnable.map((line) => ({
        key: line.sourceItem, product: line.product, name: line.productName, sold: Number(line.sold),
        limit: Number(line.returnable), price: price.get(line.sourceItem) ?? '0', quantity: '1', picked: false,
      }));
    },
  });
  const editKey = (line: PickRow) => `${invoiceId}:${line.key}`;
  const picks: PickRow[] | null = lines.data
    ? lines.data.map((line) => ({ ...line, ...edits[editKey(line)] }))
    : null;
  const patchLine = (line: PickRow, patch: Partial<PickRow>) =>
    setEdits((prev) => ({ ...prev, [editKey(line)]: { ...prev[editKey(line)], ...patch } }));
  const make = useMutation({
    mutationFn: async (action: ComplaintDocument) => {
      let items: Record<string, unknown>[];
      if (action === 'create-replacement-order') {
        items = order
          .filter((line) => line.product && Number(line.quantity) > 0)
          .map((line) => ({ product: line.product!.id, quantity: line.quantity, unit_price: line.price.trim() || String(line.product!.sellingPrice ?? '0') }));
      } else {
        items = (picks ?? [])
          .filter((line) => line.picked)
          .map((line) => (cfg.purchases
            ? { product: line.product, quantity: line.quantity, unit_price: line.price }
            : { product: line.product, quantity: line.quantity, unit_price: line.price, source_item: line.key }));
      }
      return api.document(row.id, action, items, `${cfg.kind}-${row.id}-${action}-${items.length}-${JSON.stringify(items).length}`);
    },
    onSuccess: (result) => {
      notice.ok(result.warning ? result.warning : t('care.complaints.documentMade'));
      setEdits({});
      onChanged();
    },
    onError: (err) => notice.fail(err),
  });
  const invalid = (picks ?? []).some((line) => line.picked && (!(Number(line.quantity) > 0) || Number(line.quantity) > line.limit));
  const anyPicked = (picks ?? []).some((line) => line.picked);
  const documentName = cfg.purchases ? t('care.complaints.debitNote') : t('care.complaints.creditNoteOrReturn');
  return (
    <Stack spacing={1.5} component="section" aria-label={t('care.complaints.remedies')}>
      <Typography variant="subtitle2" component="h3">{t('care.complaints.remedies')}</Typography>
      <InvoiceSelector cfg={cfg} row={row} canChange={canChange && !closed && !hasDocument} onChanged={onChanged} notice={notice} />
      <Stack spacing={0.5}>
        {cfg.documents.map((name) => {
          const docId = (row as unknown as Record<string, number | null>)[name];
          return docId ? (
            <DocumentLine key={name} name={name} id={docId} complaintId={row.id} cfg={cfg} canChange={canChange && !closed} onChanged={onChanged} notice={notice} />
          ) : null;
        })}
        {!hasDocument ? <Typography variant="body2" color="text.secondary">{t('care.complaints.noDocuments')}</Typography> : null}
      </Stack>
      {!canChange || closed ? null : !approved ? (
        <Typography variant="caption" color="text.secondary">{t('care.complaints.approveFirst')}</Typography>
      ) : !hasDocument || (!cfg.purchases && !row.replacementOrder) ? (
        <Stack spacing={1}>
          {!invoiceId ? <Typography variant="body2" color="warning.main">{t('care.complaints.pickInvoiceFirst')}</Typography> : null}
          {invoiceId && picks && !hasDocument ? (
            <>
              <Typography variant="caption" color="text.secondary">{t('care.complaints.pickLines', { document: documentName })}</Typography>
              <Table size="small" aria-label={t('care.complaints.remedies')}>
                <TableHead>
                  <TableRow>
                    <TableCell padding="checkbox"><VisuallyHidden>{t('care.common.include')}</VisuallyHidden></TableCell>
                    <TableCell scope="col">{t('growth.product')}</TableCell>
                    <TableCell scope="col" align="right">{t('care.complaints.canReturn')}</TableCell>
                    <TableCell scope="col" align="right">{t('growth.quantity')}</TableCell>
                    <TableCell scope="col" align="right">{t('growth.unitPrice')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {picks.map((line) => (
                    <TableRow key={line.key} selected={line.picked}>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={line.picked}
                          disabled={line.limit <= 0}
                          onChange={(e) => patchLine(line, { picked: e.target.checked })}
                          inputProps={{ 'aria-label': t('care.complaints.pickLine', { name: line.name }) }}
                        />
                      </TableCell>
                      <TableCell>{line.name}</TableCell>
                      <TableCell align="right">{plainNumber(line.limit)}</TableCell>
                      <TableCell align="right">
                        <TextField
                          size="small"
                          value={line.quantity}
                          disabled={!line.picked}
                          error={line.picked && (Number(line.quantity) > line.limit || !(Number(line.quantity) > 0))}
                          onChange={(e) => patchLine(line, { quantity: e.target.value })}
                          inputProps={{ 'aria-label': t('care.complaints.quantityOf', { name: line.name }), inputMode: 'decimal', style: { textAlign: 'right', width: 70 } }}
                        />
                      </TableCell>
                      <TableCell align="right">{formatMoney(line.price)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {invalid ? <Typography variant="caption" color="error" role="alert">{t('care.complaints.overReturn')}</Typography> : null}
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {cfg.purchases ? (
                  <Button size="small" variant="contained" disabled={!anyPicked || invalid || make.isPending} onClick={() => make.mutate('create-debit-note')}>
                    {t('care.complaints.createDebitNote')}
                  </Button>
                ) : (
                  <>
                    <Button size="small" variant="contained" disabled={!anyPicked || invalid || make.isPending} onClick={() => make.mutate('create-credit-note')}>
                      {t('growth.createCreditNote')}
                    </Button>
                    <Button size="small" variant="outlined" disabled={!anyPicked || invalid || make.isPending} onClick={() => make.mutate('create-return')}>
                      {t('growth.createReturn')}
                    </Button>
                  </>
                )}
              </Stack>
            </>
          ) : null}
          {invoiceId && lines.isLoading ? <Typography variant="body2">{t('common.loading')}</Typography> : null}
          {lines.isError ? <Typography variant="body2" color="error">{getErrorMessage(lines.error)}</Typography> : null}
          {!cfg.purchases && !row.replacementOrder ? (
            <Stack spacing={1}>
              <Typography variant="caption" color="text.secondary">{t('care.complaints.replacementHelp')}</Typography>
              {order.map((line, index) => (
                <Stack key={index} direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <CatalogPicker
                    kind="GOODS"
                    value={line.product}
                    onChange={(product) => setOrder((prev) => prev.map((item, i) => (i === index ? { ...item, product, price: product ? String(product.sellingPrice ?? '') : '' } : item)))}
                  />
                  <TextField size="small" label={t('growth.quantity')} value={line.quantity} onChange={(e) => setOrder((prev) => prev.map((item, i) => (i === index ? { ...item, quantity: e.target.value } : item)))} sx={{ width: 100 }} />
                  <TextField size="small" label={t('growth.unitPrice')} value={line.price} onChange={(e) => setOrder((prev) => prev.map((item, i) => (i === index ? { ...item, price: e.target.value } : item)))} sx={{ width: 120 }} />
                </Stack>
              ))}
              <Stack direction="row" spacing={1}>
                <Button size="small" onClick={() => setOrder((prev) => [...prev, { product: null, quantity: '1', price: '' }])}>{t('growth.addLine')}</Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={!order.some((line) => line.product && Number(line.quantity) > 0) || make.isPending}
                  onClick={() => make.mutate('create-replacement-order')}
                >
                  {t('growth.createReplacement')}
                </Button>
              </Stack>
            </Stack>
          ) : null}
        </Stack>
      ) : null}
    </Stack>
  );
}

function InvoiceSelector({
  cfg,
  row,
  canChange,
  onChanged,
  notice,
}: {
  cfg: Cfg;
  row: Complaint;
  canChange: boolean;
  onChanged: () => void;
  notice: ReturnType<typeof useNotice>;
}) {
  const api = complaints(cfg.kind);
  const partyId = (cfg.purchases ? row.supplier : row.customer) ?? null;
  const current = useQuery({
    queryKey: ['care-source-doc', cfg.kind, row.sourceInvoice],
    enabled: Boolean(row.sourceInvoice),
    queryFn: async () => (cfg.purchases ? await getPurchase(row.sourceInvoice!) : await getSalesInvoice(row.sourceInvoice!)),
  });
  const change = useMutation({
    mutationFn: (next: number | null) => api.update(row.id, { source_invoice: next }, row.updatedAt),
    onSuccess: () => { notice.ok(t('care.tickets.saved')); onChanged(); },
    onError: (err) => notice.fail(err),
  });
  if (!canChange) {
    return (
      <Field label={cfg.purchases ? t('care.complaints.bill') : t('growth.sourceInvoice')}>
        {row.sourceInvoice ? (
          <Link component={RouterLink} to={cfg.purchases ? `/purchases/invoices/${row.sourceInvoice}` : `/sales/history/${row.sourceInvoice}`}>
            {row.sourceInvoiceNumber || `#${row.sourceInvoice}`}
          </Link>
        ) : null}
      </Field>
    );
  }
  const value = (current.data ?? (row.sourceInvoice ? ({ id: row.sourceInvoice, number: row.sourceInvoiceNumber } as never) : null)) as SalesInvoice | null;
  return cfg.purchases ? (
    <EntityPicker<PurchaseInvoice>
      label={t('care.complaints.bill')}
      value={value as unknown as PurchaseInvoice | null}
      onChange={(next) => change.mutate(next ? next.id : null)}
      queryKey={['bill', partyId]}
      search={async (q) => (await listPurchasesPage({ supplier: partyId ?? undefined, q: q || undefined, pageSize: 20 })).results}
      getLabel={(item) => item.number || `#${item.id}`}
    />
  ) : (
    <InvoicePicker customerId={partyId} value={value} onChange={(next) => change.mutate(next ? next.id : null)} helperText={t('care.complaints.invoiceLockHelp')} />
  );
}

function DocumentLine({
  name,
  id,
  complaintId,
  cfg,
  canChange,
  onChanged,
  notice,
}: {
  name: string;
  id: number;
  complaintId: number;
  cfg: Cfg;
  canChange: boolean;
  onChanged: () => void;
  notice: ReturnType<typeof useNotice>;
}) {
  const api = complaints(cfg.kind);
  const doc = useQuery({
    queryKey: ['care-doc', name, id],
    queryFn: async (): Promise<{ number: string; status: string; href: string }> => {
      if (name === 'salesReturn') {
        const row = await getSalesReturn(id);
        return { number: row.number || `#${id}`, status: row.status, href: `/sales/returns?return=${id}` };
      }
      if (name === 'salesCreditNote') {
        const row = await getSalesCreditNote(id);
        return { number: row.number || `#${id}`, status: row.status, href: `/sales/credit-notes/${id}` };
      }
      if (name === 'replacementOrder') {
        const row = await getSalesOrder(id);
        return { number: row.number || `#${id}`, status: row.status, href: `/sales/orders/${id}` };
      }
      const row = await getPurchaseDebitNote(id);
      return { number: row.number || `#${id}`, status: row.status, href: `/purchases/debit-notes/${id}` };
    },
  });
  const unlink = useMutation({
    mutationFn: () => api.unlink(complaintId, name.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`)),
    onSuccess: () => { notice.ok(t('care.complaints.unlinked')); onChanged(); },
    onError: (err) => notice.fail(err),
  });
  const complete = useMutation({
    mutationFn: () => completeWithConfirms((extra) => completeSalesCreditNote(id, extra)),
    onSuccess: () => { void doc.refetch(); onChanged(); notice.ok(t('care.complaints.noteCompleted')); },
    onError: (err) => notice.fail(err),
  });
  const kindLabel = t(`care.complaints.doc.${name}`);
  const data = doc.data;
  return (
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Typography variant="body2">{kindLabel}:</Typography>
      {data ? (
        <Link component={RouterLink} to={data.href}>{data.number}</Link>
      ) : (
        <Typography variant="body2">#{id}</Typography>
      )}
      {data ? <Typography variant="caption" color="text.secondary">{data.status}</Typography> : null}
      {canChange && data?.status === 'DRAFT' && name === 'salesCreditNote' ? (
        <Button size="small" variant="contained" disabled={complete.isPending} onClick={() => complete.mutate()}>{t('growth.completeCreditNote')}</Button>
      ) : null}
      {canChange && data?.status === 'CANCELLED' ? (
        <Button size="small" color="warning" disabled={unlink.isPending} onClick={() => unlink.mutate()}>{t('care.complaints.unlink')}</Button>
      ) : null}
      {data && data.status === 'CANCELLED' ? <Typography variant="caption" color="warning.main">{t('care.complaints.cancelledDoc')}</Typography> : null}
    </Stack>
  );
}

