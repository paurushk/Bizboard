import type { ReactNode } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';

export type HistoryFilters = {
  q: string;
  status: string;
  dateFrom: string;
  dateTo: string;
  paymentStatus?: string;
};

export const EMPTY_HISTORY_FILTERS: HistoryFilters = {
  q: '',
  status: '',
  dateFrom: '',
  dateTo: '',
};

export type HistoryStatusOption = { value: string; label: string };

export type DateRangePresetId =
  | 'today'
  | 'thisWeek'
  | 'last15'
  | 'thisMonth'
  | 'last365'
  | 'custom';

export const DATE_RANGE_PRESET_IDS: DateRangePresetId[] = [
  'today',
  'thisWeek',
  'last15',
  'thisMonth',
  'last365',
  'custom',
];

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function dateRangeForPreset(id: DateRangePresetId, now = new Date()): { dateFrom: string; dateTo: string } {
  const to = isoDate(now);
  if (id === 'custom') return { dateFrom: '', dateTo: '' };
  if (id === 'today') return { dateFrom: to, dateTo: to };
  if (id === 'last15') {
    const from = new Date(now);
    from.setDate(from.getDate() - 14);
    return { dateFrom: isoDate(from), dateTo: to };
  }
  if (id === 'last365') {
    const from = new Date(now);
    from.setDate(from.getDate() - 364);
    return { dateFrom: isoDate(from), dateTo: to };
  }
  if (id === 'thisWeek') {
    const from = new Date(now);
    const weekday = from.getDay(); // 0 Sun
    const offset = weekday === 0 ? 6 : weekday - 1; // Monday start
    from.setDate(from.getDate() - offset);
    return { dateFrom: isoDate(from), dateTo: to };
  }
  // thisMonth
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  return { dateFrom: isoDate(from), dateTo: to };
}

type Props = {
  value: HistoryFilters;
  onChange: (next: HistoryFilters) => void;
  statusOptions?: HistoryStatusOption[];
  showDateRange?: boolean;
  dateRangePresets?: boolean;
  searchPlaceholder?: string;
  bulkSelectedCount?: number;
  bulkActions?: ReactNode;
  onClearBulk?: () => void;
};

export function HistoryFilterBar({
  value,
  onChange,
  statusOptions = [],
  showDateRange = true,
  dateRangePresets = false,
  searchPlaceholder,
  bulkSelectedCount = 0,
  bulkActions,
  onClearBulk,
}: Props) {
  const set = (patch: Partial<HistoryFilters>) => onChange({ ...value, ...patch });

  const applyPreset = (id: DateRangePresetId) => {
    const range = dateRangeForPreset(id);
    set(range);
  };

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
      {dateRangePresets && showDateRange ? (
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {DATE_RANGE_PRESET_IDS.map((id) => (
            <Chip
              key={id}
              label={t(`history.preset.${id}`)}
              size="small"
              variant="outlined"
              onClick={() => applyPreset(id)}
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
      {bulkSelectedCount > 0 ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            {t('history.selectedCount', { count: bulkSelectedCount })}
          </Typography>
          {bulkActions}
          {onClearBulk ? (
            <Button size="small" onClick={onClearBulk}>
              {t('common.clear')}
            </Button>
          ) : null}
        </Stack>
      ) : null}
    </Stack>
  );
}
