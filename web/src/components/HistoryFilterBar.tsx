import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { t } from '@/i18n';

export type HistoryFilters = {
  q: string;
  status: string;
  dateFrom: string;
  dateTo: string;
};

export const EMPTY_HISTORY_FILTERS: HistoryFilters = {
  q: '',
  status: '',
  dateFrom: '',
  dateTo: '',
};

export type HistoryStatusOption = { value: string; label: string };

type Props = {
  value: HistoryFilters;
  onChange: (next: HistoryFilters) => void;
  statusOptions?: HistoryStatusOption[];
  showDateRange?: boolean;
  searchPlaceholder?: string;
};

// F2-033: the shared filter bar for history / master lists — status chips, a
// free-text search, and (optionally) an invoice-date range. Every field maps
// straight onto the list endpoints' existing params (status / q / date_from /
// date_to), so wiring is just: keep a HistoryFilters in state, feed it here,
// pass the parts into the list query and reset to page 1 on change.
export function HistoryFilterBar({
  value,
  onChange,
  statusOptions = [],
  showDateRange = true,
  searchPlaceholder,
}: Props) {
  const set = (patch: Partial<HistoryFilters>) => onChange({ ...value, ...patch });

  return (
    <Stack spacing={1.5}>
      {statusOptions.length ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Chip
            label={t('common.all')}
            size="small"
            color={value.status === '' ? 'primary' : 'default'}
            variant={value.status === '' ? 'filled' : 'outlined'}
            onClick={() => set({ status: '' })}
          />
          {statusOptions.map((opt) => (
            <Chip
              key={opt.value}
              label={opt.label}
              size="small"
              color={value.status === opt.value ? 'primary' : 'default'}
              variant={value.status === opt.value ? 'filled' : 'outlined'}
              onClick={() => set({ status: value.status === opt.value ? '' : opt.value })}
            />
          ))}
        </Stack>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap>
        <TextField
          size="small"
          placeholder={searchPlaceholder ?? t('common.search')}
          value={value.q}
          onChange={(e) => set({ q: e.target.value })}
          sx={{ minWidth: 220, flex: 1, maxWidth: 360 }}
        />
        {showDateRange ? (
          <>
            <TextField
              size="small"
              type="date"
              label={t('common.from')}
              InputLabelProps={{ shrink: true }}
              value={value.dateFrom}
              onChange={(e) => set({ dateFrom: e.target.value })}
              sx={{ maxWidth: 180 }}
            />
            <TextField
              size="small"
              type="date"
              label={t('common.to')}
              InputLabelProps={{ shrink: true }}
              value={value.dateTo}
              onChange={(e) => set({ dateTo: e.target.value })}
              sx={{ maxWidth: 180 }}
            />
          </>
        ) : null}
      </Stack>
    </Stack>
  );
}
