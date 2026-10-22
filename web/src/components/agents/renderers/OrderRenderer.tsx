import Alert from '@mui/material/Alert';
import Autocomplete from '@mui/material/Autocomplete';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { useProductSearch } from '@/hooks/useProductSearch';
import { t } from '@/i18n';
import type { Customer, Product } from '@/types/domain';
import { isOrderReady } from './ready';
import type { RendererProps } from './types';

type Alternative = { id: number; name: string; score?: number };
type OrderLine = {
  raw: string;
  rawNorm?: string;
  qty: string | null;
  unit: string;
  productId: number | null;
  productName: string;
  match?: { source: string; score: number };
  alternatives?: Alternative[];
  warnings?: string[];
};

// The API camelCases every key, payload included, and snake_cases what we send back.
type RawLine = Record<string, unknown>;

function lineOf(l: RawLine): OrderLine {
  return {
    raw: String(l.raw ?? ''),
    rawNorm: String(l.rawNorm ?? ''),
    qty: l.qty == null ? null : String(l.qty),
    unit: String(l.unit ?? ''),
    productId: typeof l.productId === 'number' ? l.productId : null,
    productName: String(l.productName ?? ''),
    match: l.match as OrderLine['match'],
    alternatives: (l.alternatives as Alternative[]) ?? [],
    warnings: (l.warnings as string[]) ?? [],
  };
}

function ProductCell({ line, disabled, onPick }: { line: OrderLine; disabled: boolean; onPick: (p: Alternative | null) => void }) {
  const selected = line.productId ? ({ id: line.productId, name: line.productName } as Product) : null;
  const search = useProductSearch({ activeOnly: true, selected });
  return (
    <Stack spacing={0.5}>
      <Autocomplete<Product>
        size="small"
        disabled={disabled}
        options={search.options}
        loading={search.isFetching}
        filterOptions={(opts) => opts}
        value={selected}
        // Show the matched product's name until the person starts typing a search.
        inputValue={search.productQuery || selected?.name || ''}
        onInputChange={(_, v, reason) => {
          if (reason === 'input' || reason === 'clear') search.setProductQuery(v);
        }}
        onChange={(_, p) => onPick(p ? { id: p.id, name: p.name } : null)}
        getOptionLabel={(p) => p.name}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        renderInput={(params) => (
          <TextField
            {...params}
            variant="standard"
            error={!line.productId}
            placeholder={t('agents.order.pickProduct')}
            inputProps={{ ...params.inputProps, 'aria-label': `${t('agents.order.product')}: ${line.raw}` }}
          />
        )}
      />
      {!line.productId && (line.alternatives?.length ?? 0) > 0 ? (
        <Stack direction="row" gap={0.5} flexWrap="wrap">
          {line.alternatives!.map((a) => (
            <Chip key={a.id} size="small" variant="outlined" label={a.name} disabled={disabled} onClick={() => onPick(a)} />
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}

/** An order read from pasted text: pick the customer, fix any product, change quantities. Prices are not shown or sent. */
export function OrderRenderer({ value, onChange, disabled }: RendererProps) {
  const lines = (Array.isArray(value.lines) ? (value.lines as RawLine[]) : []).map(lineOf);
  const customerId = typeof value.customerId === 'number' ? value.customerId : null;
  const selected = customerId ? ({ id: customerId, name: String(value.customerName ?? '') } as Customer) : null;
  const customers = useCustomerSearch({ selected, activeOnly: true });
  const alternatives = (value.customerAlternatives as Alternative[]) ?? [];
  const warnings = (value.warnings as string[]) ?? [];

  function pickCustomer(c: { id: number; name: string } | null) {
    onChange({
      ...value,
      customerId: c ? c.id : null,
      customerName: c ? c.name : '',
      customerMatch: { source: c ? 'manual' : 'none', score: c ? 1 : 0 },
    });
  }

  function setLine(index: number, patch: RawLine) {
    const next = (value.lines as RawLine[]).map((l, i) => (i === index ? { ...l, ...patch } : l));
    onChange({ ...value, lines: next });
  }

  return (
    <Stack spacing={2}>
      {warnings.map((w) => (
        <Alert key={w} severity="warning">{w}</Alert>
      ))}
      <Stack spacing={0.5}>
        <Autocomplete<Customer>
          size="small"
          disabled={disabled}
          options={customers.options}
          loading={customers.isFetching}
          filterOptions={(opts) => opts}
          value={selected}
          inputValue={customers.query || selected?.name || ''}
          onInputChange={(_, v, reason) => {
            if (reason === 'input' || reason === 'clear') customers.setQuery(v);
          }}
          onChange={(_, c) => pickCustomer(c ? { id: c.id, name: c.name } : null)}
          getOptionLabel={(c) => c.name}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField {...params} label={t('agents.order.customer')} error={!selected} helperText={value.customerHint ? t('agents.order.wrote', { text: String(value.customerHint) }) : undefined} />
          )}
        />
        {!selected && alternatives.length > 0 ? (
          <Stack direction="row" gap={0.5} flexWrap="wrap">
            {alternatives.map((a) => (
              <Chip key={a.id} size="small" variant="outlined" label={a.name} disabled={disabled} onClick={() => pickCustomer(a)} />
            ))}
          </Stack>
        ) : null}
      </Stack>

      <Stack spacing={1.5} component="ul" sx={{ listStyle: 'none', p: 0, m: 0 }} aria-label={t('agents.order.lines')}>
        {lines.map((line, i) => (
          <Stack key={`${i}:${line.raw}`} component="li" spacing={0.5} sx={{ borderLeft: 3, borderColor: line.productId && line.qty ? 'divider' : 'warning.main', pl: 1.5 }}>
            <Typography variant="caption" color="text.secondary">{t('agents.order.wrote', { text: line.raw })}</Typography>
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                size="small"
                variant="standard"
                sx={{ width: 84 }}
                value={line.qty ?? ''}
                disabled={disabled}
                error={!line.qty || Number(line.qty) <= 0}
                onChange={(e) => setLine(i, { qty: e.target.value })}
                inputProps={{ inputMode: 'decimal', 'aria-label': `${t('agents.lines.qty')} ${i + 1}` }}
              />
              <Typography variant="body2" sx={{ pt: 0.5, minWidth: 32 }}>{line.unit}</Typography>
              <div style={{ flex: 1 }}>
                <ProductCell
                  line={line}
                  disabled={disabled}
                  onPick={(p) =>
                    setLine(i, p
                      ? { productId: p.id, productName: p.name, match: { source: 'manual', score: 1 } }
                      : { productId: null, productName: '', match: { source: 'none', score: 0 } })}
                />
              </div>
            </Stack>
            {(line.warnings ?? []).map((w) => (
              <Typography key={w} variant="caption" color="warning.main">{w}</Typography>
            ))}
          </Stack>
        ))}
      </Stack>
      {!isOrderReady(value) ? <Alert severity="info">{t('agents.order.incomplete')}</Alert> : null}
    </Stack>
  );
}
