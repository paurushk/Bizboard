import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  contractReport,
  contractTimeline,
  createContract,
  createContractSchedule,
  deleteContractAttachment,
  listContractAttachments,
  listContractsPage,
  logServiceEvent,
  updateContract,
  uploadContractAttachment,
  type ContractRow,
} from '@/api/growth';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { CreateDialog } from '@/components/CreateDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { isContractsEnabled } from '@/config/features';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { t } from '@/i18n';
import { AttachmentEditor, CustomerField, ProductField, localDateInput } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer, Product } from '@/types/domain';

const TYPES = ['WARRANTY', 'AMC', 'SUBSCRIPTION', 'INSURANCE', 'OTHER'] as const;

export function ContractsPage() {
  if (!isContractsEnabled()) {
    return <PageShell title={t('nav.contracts')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <ContractsInner />;
}

function ContractsInner() {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [contractType, setContractType] = useState('WARRANTY');
  const [startDate, setStartDate] = useState(localDateInput);
  const [endDate, setEndDate] = useState('');
  const [value, setValue] = useState('');
  const [notes, setNotes] = useState('');
  const [reminder, setReminder] = useState('30');
  const [products, setProducts] = useState<Product[]>([]);
  const [draftProduct, setDraftProduct] = useState<Product | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [more, setMore] = useState(false);
  const [error, setError] = useState('');
  const list = useQuery({
    queryKey: ['contracts', page, q, statusFilter],
    queryFn: () => listContractsPage({ page, pageSize: 20, q: q.trim() || undefined, status: statusFilter || undefined, customer: undefined }),
  });
  const report = useQuery({ queryKey: ['contract-report'], queryFn: contractReport });
  const create = useMutation({
    mutationFn: () => createContract({
      customer: customer!.id,
      product: products[0]?.id ?? null,
      products: products.map((item) => item.id),
      contract_type: contractType,
      start_date: startDate,
      end_date: endDate,
      value: value || null,
      notes,
      renewal_reminder_days: Number(reminder),
    }),
    onSuccess: () => {
      setError('');
      setCreateOpen(false);
      setMore(false);
      void qc.invalidateQueries({ queryKey: ['contracts'] });
      void qc.invalidateQueries({ queryKey: ['contract-report'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.contracts')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.valueCopiesToSchedule')}</Typography>
      <Stack direction="row" spacing={1}>
        <TextField size="small" label={t('cog.searchGrowth')} value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <TextField size="small" label={t('common.status')} value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} />
      </Stack>
      <Button sx={{ alignSelf: 'flex-start' }} variant="contained" onClick={() => setCreateOpen(true)}>{t('growth.addContract')}</Button>
      <CreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title={t('growth.addContract')}
        submitLabel={t('growth.addContract')}
        submitDisabled={!customer || !endDate || !/^\d+$/.test(reminder) || create.isPending}
        dirty={Boolean(customer || notes || value)}
        onSubmit={() => create.mutate()}
      >
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField select size="small" label={t('growth.type')} value={contractType} onChange={(e) => setContractType(e.target.value)}>
          {TYPES.map((item) => <MenuItem key={item} value={item}>{enumLabel('contractType', item)}</MenuItem>)}
        </TextField>
        <TextField size="small" type="date" label={t('growth.startDate')} value={startDate} onChange={(e) => setStartDate(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" type="date" label={t('growth.endDate')} value={endDate} onChange={(e) => setEndDate(e.target.value)} InputLabelProps={{ shrink: true }} />
        <TextField size="small" label={t('growth.value')} value={value} onChange={(e) => setValue(e.target.value)} helperText={t('growth.valueCopiesToSchedule')} />
        <Button size="small" onClick={() => setMore((open) => !open)}>{t('growth.more')}</Button>
        {more ? (
          <>
            <TextField size="small" label={t('growth.reminderDays')} value={reminder} onChange={(e) => setReminder(e.target.value)} />
            <TextField size="small" label={t('growth.notes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
            <ProductField value={draftProduct} onChange={setDraftProduct} />
            <Button size="small" disabled={!draftProduct} onClick={() => {
              if (!draftProduct || products.some((item) => item.id === draftProduct.id)) return;
              setProducts((current) => [...current, draftProduct]);
              setDraftProduct(null);
            }}>{t('growth.addLine')}</Button>
            {products.length ? (
              <Typography variant="body2">{products.map((item) => item.name).join(', ')}</Typography>
            ) : null}
          </>
        ) : null}
        {error ? <Typography color="error">{error}</Typography> : null}
      </CreateDialog>
      {list.isLoading ? <LoadingState /> : null}
      {list.isError ? <ErrorState message={getErrorMessage(list.error)} error={list.error} onRetry={() => void list.refetch()} /> : null}
      {!list.isLoading && !list.isError && (list.data?.results ?? []).length === 0 ? (
        <EmptyState description={t('cog.emptyContracts')} action={<Button variant="contained" onClick={() => setCreateOpen(true)}>{t('common.add')}</Button>} />
      ) : null}
      {error ? <Typography color="error">{error}</Typography> : null}
      {(list.data?.results ?? []).map((row) => (
        <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction="row" justifyContent="space-between">
            <Typography>{row.number} · {enumLabel('contractType', row.contractType)} · {enumLabel('contractStatus', row.status)} · {row.endDate} · {row.value ?? '—'}</Typography>
            <Stack direction="row" spacing={1}>
              <Button size="small" onClick={() => setSelected(row.id)}>{t('growth.detail')}</Button>
            </Stack>
          </Stack>
        </Paper>
      ))}
      <Stack direction="row" spacing={1}>
        <Button size="small" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>{t('common.previous')}</Button>
        <Button size="small" disabled={!list.data?.next} onClick={() => setPage((p) => p + 1)}>{t('common.next')}</Button>
      </Stack>
      {selected ? <ContractDetail key={selected} id={selected} row={(list.data?.results ?? []).find((row) => row.id === selected) ?? null} onError={setError} /> : null}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2">{t('growth.report')}</Typography>
        {(report.data ?? []).map((row) => (
          <Typography key={`${row.status}-${row.contractType}`} variant="body2">{enumLabel('contractStatus', row.status)} · {enumLabel('contractType', row.contractType)} · {formatMoney(row.value ?? 0)}</Typography>
        ))}
      </Paper>
    </Stack>
  );
}

function ContractDetail({ id, row, onError }: { id: number; row: ContractRow | null; onError: (message: string) => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [cancelOpen, setCancelOpen] = useState(false);
  const [renewing, setRenewing] = useState(false);
  const [notes, setNotes] = useState('');
  const [ticketId, setTicketId] = useState('');
  const timeline = useQuery({ queryKey: ['contract-timeline', id], queryFn: () => contractTimeline(id) });
  const files = useQuery({ queryKey: ['contract-files', id], queryFn: () => listContractAttachments(id) });
  const run = useMutation({
    mutationFn: async (work: () => Promise<unknown>) => work(),
    onSuccess: () => {
      onError('');
      void qc.invalidateQueries({ queryKey: ['contracts'] });
      void qc.invalidateQueries({ queryKey: ['contract-timeline', id] });
      void qc.invalidateQueries({ queryKey: ['contract-files', id] });
      void qc.invalidateQueries({ queryKey: ['contract-report'] });
    },
    onError: (err) => onError(getErrorMessage(err)),
  });
  if (!row) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle2">{row.number} · {enumLabel('contractStatus', row.status)}</Typography>
      <Typography variant="body2">{t('growth.warrantyPeriod')}: {new Date(row.startDate).toLocaleDateString('en-IN')} – {row.endDate ? new Date(row.endDate).toLocaleDateString('en-IN') : ''}</Typography>
      <Typography variant="body2">{row.notes}</Typography>
      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
        {row.status !== 'CANCELLED' ? (
          <Button size="small" onClick={() => setCancelOpen(true)}>{t('growth.cancel')}</Button>
        ) : (
          <Button size="small" onClick={() => run.mutate(() => updateContract(id, { status: 'ACTIVE' }))}>{t('growth.uncancel')}</Button>
        )}
        <Button size="small" disabled={renewing} onClick={() => {
          // This creates an invoice: ask first, and ignore a second click while it runs.
          if (renewing || !window.confirm(`${t('cog.renewInvoice')}?`)) return;
          setRenewing(true);
          void createContractSchedule(id).then((row) => {
            if (row.invoice) navigate(`/sales/history/${row.invoice}`);
          }).catch((err) => onError(getErrorMessage(err))).finally(() => setRenewing(false));
        }}>{t('cog.renewInvoice')}</Button>
      </Stack>
      <ConfirmDialog
        open={cancelOpen}
        title={t('cog.confirmCancelContract', { name: row.number })}
        body={row.number}
        requireTyped={row.number}
        confirmColor="error"
        onClose={() => setCancelOpen(false)}
        onConfirm={() => {
          setCancelOpen(false);
          run.mutate(() => updateContract(id, { status: 'CANCELLED' }));
        }}
      />
      <Typography variant="subtitle2" sx={{ mt: 2 }}>{t('growth.timeline')}</Typography>
      {(timeline.data?.events ?? []).map((event) => (
        <Typography key={event.id} variant="body2">{event.occurredAt} · {event.notes}{event.ticket ? ` · #${event.ticket}` : ''}</Typography>
      ))}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} sx={{ mt: 1 }}>
        <TextField size="small" label={t('growth.notes')} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <TextField size="small" label={t('growth.ticketId')} value={ticketId} onChange={(e) => setTicketId(e.target.value)} />
        <Button disabled={!notes.trim() || (ticketId.trim() !== '' && !/^\d+$/.test(ticketId.trim()))} onClick={() => run.mutate(async () => {
          await logServiceEvent(id, { notes, ticket: ticketId.trim() ? Number(ticketId) : undefined });
          setNotes('');
          setTicketId('');
        })}>{t('growth.serviceEvent')}</Button>
      </Stack>
      <AttachmentEditor
        rows={files.data ?? []}
        onUpload={(file) => run.mutate(() => uploadContractAttachment(id, file))}
        onDelete={(attachmentId) => run.mutate(() => deleteContractAttachment(id, attachmentId))}
      />
    </Paper>
  );
}
