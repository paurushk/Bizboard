/** Ready-made pickers for the records the care and job screens point at (FND-04). */
import { bays, contracts, jobs, tickets, type Contract, type Job, type ServiceBay, type Ticket } from '@/api/care';
import { listProductsPage, listSalesInvoicesPage, listWarehouses } from '@/api/resources';
import { useQuery } from '@tanstack/react-query';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';
import type { Product, SalesInvoice } from '@/types/domain';
import { formatDay } from './format';
import { EntityPicker } from './kit';

type PickerProps<T> = {
  value: T | null;
  onChange: (next: T | null) => void;
  disabled?: boolean;
  required?: boolean;
  helperText?: string;
};

export function InvoicePicker({
  customerId,
  completedOnly = true,
  label,
  ...rest
}: PickerProps<SalesInvoice> & { customerId: number | null; completedOnly?: boolean; label?: string }) {
  return (
    <EntityPicker<SalesInvoice>
      {...rest}
      label={label ?? t('care.pick.invoice')}
      disabled={rest.disabled || customerId == null}
      queryKey={['invoice', customerId, completedOnly]}
      search={async (q) =>
        (await listSalesInvoicesPage({
          customer: customerId ?? undefined,
          q: q || undefined,
          pageSize: 20,
          ...(completedOnly ? { status: 'COMPLETED' } : {}),
        })).results
      }
      getLabel={(row) => `${row.number || `#${row.id}`} · ${formatDay(row.invoiceDate)}`}
    />
  );
}

export function TicketPicker({ customerId, label, ...rest }: PickerProps<Ticket> & { customerId: number | null; label?: string }) {
  return (
    <EntityPicker<Ticket>
      {...rest}
      label={label ?? t('care.pick.ticket')}
      disabled={rest.disabled || customerId == null}
      queryKey={['ticket', customerId]}
      search={async (q) =>
        (await tickets.list({ customer: customerId ?? undefined, q: q || undefined, pageSize: 20 })).results
      }
      getLabel={(row) => `${row.number} · ${row.subject}`}
    />
  );
}

export function ContractPicker({
  customerId,
  label,
  ...rest
}: PickerProps<Contract> & { customerId: number | null; label?: string }) {
  return (
    <EntityPicker<Contract>
      {...rest}
      label={label ?? t('care.pick.contract')}
      disabled={rest.disabled || customerId == null}
      queryKey={['contract', customerId]}
      search={async (q) =>
        (await contracts.list({ customer: customerId ?? undefined, q: q || undefined, pageSize: 20 })).results
      }
      getLabel={(row) => `${row.number} · ${formatDay(row.startDate)} – ${formatDay(row.endDate)}`}
    />
  );
}

export function JobPicker({ label, ...rest }: PickerProps<Job> & { label?: string }) {
  return (
    <EntityPicker<Job>
      {...rest}
      label={label ?? t('care.pick.job')}
      queryKey={['job']}
      search={async (q) => (await jobs.list({ q: q || undefined, pageSize: 20 })).results}
      getLabel={(row) => `${row.number} · ${row.customerName}${row.registrationNo ? ` · ${row.registrationNo}` : ''}`}
    />
  );
}

export function BayPicker({ label, ...rest }: PickerProps<ServiceBay> & { label?: string }) {
  return (
    <EntityPicker<ServiceBay>
      {...rest}
      label={label ?? t('care.pick.bay')}
      queryKey={['bay']}
      minWidth={180}
      search={async (q) => {
        const rows = (await bays.list()).results;
        return q ? rows.filter((row) => row.name.toLowerCase().includes(q.toLowerCase())) : rows;
      }}
      getLabel={(row) => row.name}
    />
  );
}

/**
 * Which godown a job takes its parts from. A company with a single godown never sees this; a person who
 * cannot read warehouses gets the default silently (JOB-13).
 */
export function WarehousePicker({ value, onChange, disabled }: { value: number | null; onChange: (id: number | null) => void; disabled?: boolean }) {
  const list = useQuery({
    queryKey: ['care-pick', 'warehouse'],
    queryFn: () => listWarehouses().catch(() => []),
    staleTime: 60_000,
  });
  const rows = (list.data ?? []).filter((row) => row.isActive !== false);
  if (rows.length < 2) return null;
  return (
    <TextField
      select
      size="small"
      label={t('care.jobs.warehouse')}
      value={value ?? ''}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))}
      helperText={t('care.jobs.warehouseHelp')}
    >
      <MenuItem value="">{t('care.jobs.warehouseDefault')}</MenuItem>
      {rows.map((row) => <MenuItem key={row.id} value={row.id}>{row.name}</MenuItem>)}
    </TextField>
  );
}

/** Parts are stock items; labour and project work are services. */
export function CatalogPicker({
  kind,
  label,
  ...rest
}: PickerProps<Product> & { kind: 'GOODS' | 'SERVICE' | 'ANY'; label?: string }) {
  return (
    <EntityPicker<Product>
      {...rest}
      label={label ?? (kind === 'GOODS' ? t('care.pick.part') : kind === 'SERVICE' ? t('care.pick.service') : t('care.pick.product'))}
      queryKey={['catalog', kind]}
      search={async (q) =>
        (await listProductsPage({
          q: q || undefined,
          pageSize: 25,
          status: 'ACTIVE',
          ...(kind === 'ANY' ? {} : { product_type: kind }),
        } as never)).results
      }
      getLabel={(row) => `${row.name}${row.sku ? ` · ${row.sku}` : ''}`}
    />
  );
}
