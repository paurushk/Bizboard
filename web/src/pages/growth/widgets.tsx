import { useRef, useState } from 'react';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useCustomerSearch, useSupplierSearch } from '@/hooks/usePartySearch';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import type { Customer, Product, Supplier } from '@/types/domain';
import type { AttachmentRow } from '@/api/growth';

export function localDateInput(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

export function CustomerField({
  value,
  onChange,
}: {
  value: Customer | null;
  onChange: (customer: Customer | null) => void;
}) {
  const search = useCustomerSearch({ selected: value });
  return (
    <Autocomplete
      options={search.options}
      getOptionLabel={(option) => `${option.name}${option.phone ? ` (${option.phone})` : ''}`}
      filterOptions={(options) => options}
      value={value}
      onChange={(_, next) => onChange(next)}
      onInputChange={(_, next) => search.setQuery(next)}
      loading={search.isFetching}
      sx={{ minWidth: 240 }}
      renderInput={(params) => <TextField {...params} size="small" label={t('growth.customer')} />}
    />
  );
}

export function SupplierField({
  value,
  onChange,
}: {
  value: Supplier | null;
  onChange: (supplier: Supplier | null) => void;
}) {
  const search = useSupplierSearch({ selected: value });
  return (
    <Autocomplete
      options={search.options}
      getOptionLabel={(option) => option.name}
      filterOptions={(options) => options}
      value={value}
      onChange={(_, next) => onChange(next)}
      onInputChange={(_, next) => search.setQuery(next)}
      loading={search.isFetching}
      sx={{ minWidth: 240 }}
      renderInput={(params) => <TextField {...params} size="small" label={t('growth.supplier')} />}
    />
  );
}

export function ProductField({
  value,
  onChange,
  label,
}: {
  value: Product | null;
  onChange: (product: Product | null) => void;
  label?: string;
}) {
  const search = useProductSearch({ activeOnly: true, selected: value });
  return (
    <Autocomplete
      options={search.options}
      getOptionLabel={(option) => option.name}
      filterOptions={(options) => options}
      value={value}
      onChange={(_, next) => onChange(next)}
      onInputChange={(_, next) => search.setProductQuery(next)}
      loading={search.isFetching}
      sx={{ minWidth: 220 }}
      renderInput={(params) => <TextField {...params} size="small" label={label ?? t('growth.product')} />}
    />
  );
}

export function AttachmentEditor({
  rows,
  onUpload,
  onDelete,
}: {
  rows: AttachmentRow[];
  onUpload: (file: File) => void;
  onDelete: (id: number) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<number | null>(null);
  return (
    <Stack spacing={1}>
      <Typography variant="subtitle2">{t('growth.attachments')}</Typography>
      <Typography variant="caption" color="text.secondary">{t('growth.attachmentHint')}</Typography>
      {rows.map((row) => (
        <Stack key={row.id} direction="row" spacing={1} alignItems="center">
          <Typography variant="body2">#{row.file}</Typography>
          <Button size="small" aria-label={t('cog.deleteAttachment')} onClick={() => setPending(row.id)}>{t('growth.remove')}</Button>
        </Stack>
      ))}
      <Button size="small" variant="outlined" onClick={() => input.current?.click()}>{t('growth.upload')}</Button>
      <input
        ref={input}
        hidden
        type="file"
        accept="image/jpeg,image/png,image/webp,application/pdf"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
          event.target.value = '';
        }}
      />
      <ConfirmDialog
        open={pending != null}
        title={t('cog.deleteAttachment')}
        body={`#${pending ?? ''}`}
        requireTyped={pending != null ? `#${pending}` : undefined}
        confirmColor="error"
        onClose={() => setPending(null)}
        onConfirm={() => {
          if (pending != null) onDelete(pending);
          setPending(null);
        }}
      />
    </Stack>
  );
}
