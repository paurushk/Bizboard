import { useState, type ReactNode } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
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
  /** Only bills past their due date with money still due. */
  overdue?: boolean;
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
  | 'currentFY'
  | 'previousFY'
  | 'q1'
  | 'q2'
  | 'q3'
  | 'q4'
  | 'custom';

export const DATE_RANGE_PRESET_IDS: DateRangePresetId[] = [
  'today',
  'thisWeek',
  'last15',
  'thisMonth',
  'currentFY',
  'previousFY',
  'q1',
  'q2',
  'q3',
  'q4',
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
  const fyStartYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  if (id === 'currentFY') {
    return { dateFrom: isoDate(new Date(fyStartYear, 3, 1)), dateTo: isoDate(new Date(fyStartYear + 1, 2, 31)) };
  }
  if (id === 'previousFY') {
    return { dateFrom: isoDate(new Date(fyStartYear - 1, 3, 1)), dateTo: isoDate(new Date(fyStartYear, 2, 31)) };
  }
  const quarterStart: Record<'q1' | 'q2' | 'q3' | 'q4', [number, number]> = {
    q1: [fyStartYear, 3],
    q2: [fyStartYear, 6],
    q3: [fyStartYear, 9],
    q4: [fyStartYear + 1, 0],
  };
  if (id === 'q1' || id === 'q2' || id === 'q3' || id === 'q4') {
    const [year, month] = quarterStart[id];
    const end = new Date(year, month + 3, 0);
    return { dateFrom: isoDate(new Date(year, month, 1)), dateTo: isoDate(end) };
  }
  // thisMonth
  const from = new Date(now.getFullYear(), now.getMonth(), 1);
  return { dateFrom: isoDate(from), dateTo: to };
}

export function activeDatePreset(
  dateFrom: string,
  dateTo: string,
  now = new Date(),
): DateRangePresetId | '' {
  if (!dateFrom && !dateTo) return '';
  for (const id of DATE_RANGE_PRESET_IDS) {
    if (id === 'custom') continue;
    const range = dateRangeForPreset(id, now);
    if (range.dateFrom === dateFrom && range.dateTo === dateTo) return id;
  }
  return 'custom';
}

type Props = {
  value: HistoryFilters;
  onChange: (next: HistoryFilters) => void;
  statusOptions?: HistoryStatusOption[];
  showDateRange?: boolean;
  dateRangePresets?: boolean;
  dateControl?: 'chips' | 'preset';
  searchLabel?: string;
  searchPlaceholder?: string;
  bulkSelectedCount?: number;
  bulkActions?: ReactNode;
  onClearBulk?: () => void;
  party?: ReactNode;
  /**
   * 'stacked' (default) keeps every control on its own row. 'compact' puts the status chips and
   * `actions` on one row, search / date / party / `controls` on a wrapping second row, and
   * `footer` (quick-filter chips) on a third.
   */
  layout?: 'stacked' | 'compact';
  actions?: ReactNode;
  controls?: ReactNode;
  footer?: ReactNode;
};

export function HistoryFilterBar({
  value,
  onChange,
  statusOptions = [],
  showDateRange = true,
  dateRangePresets = false,
  dateControl = 'chips',
  searchLabel,
  searchPlaceholder,
  bulkSelectedCount = 0,
  bulkActions,
  onClearBulk,
  party,
  layout = 'stacked',
  actions,
  controls,
  footer,
}: Props) {
  const set = (patch: Partial<HistoryFilters>) => onChange({ ...value, ...patch });
  const [forceCustom, setForceCustom] = useState(false);
  const derivedPreset = activeDatePreset(value.dateFrom, value.dateTo);
  const presetValue = derivedPreset || (forceCustom ? 'custom' : '');
  const showDateFields = dateControl === 'chips' || derivedPreset === 'custom' || forceCustom;

  const applyPreset = (id: DateRangePresetId | '') => {
    if (id === '') {
      setForceCustom(false);
      set({ dateFrom: '', dateTo: '' });
      return;
    }
    setForceCustom(id === 'custom');
    set(dateRangeForPreset(id));
  };

  const compact = layout === 'compact';
  const searchField = (
    <TextField
      size="small"
      label={searchLabel}
      placeholder={searchPlaceholder ?? t('common.search')}
      value={value.q}
      onChange={(e) => set({ q: e.target.value })}
      sx={compact ? { flex: '2 1 260px', minWidth: 0, maxWidth: { sm: 440 } } : { minWidth: 220, flex: 1, maxWidth: 360 }}
      inputProps={searchLabel ? { 'aria-label': searchLabel } : undefined}
    />
  );
  const dateSelect = (
    <TextField
      select
      size="small"
      label={t('history.dateRange')}
      value={presetValue}
      onChange={(event) => applyPreset(event.target.value as DateRangePresetId | '')}
      sx={compact ? { flex: '1 1 190px', minWidth: 0, maxWidth: { sm: 260 } } : { maxWidth: 280 }}
    >
      <MenuItem value="">{t('common.all')}</MenuItem>
      {DATE_RANGE_PRESET_IDS.map((id) => (
        <MenuItem key={id} value={id}>
          {t(`history.preset.${id}`)}
        </MenuItem>
      ))}
    </TextField>
  );
  const dateFields = (
    <>
      <TextField
        size="small"
        type="date"
        label={t('common.from')}
        InputLabelProps={{ shrink: true }}
        value={value.dateFrom}
        onChange={(e) => set({ dateFrom: e.target.value })}
        sx={compact ? { flex: '1 1 150px', minWidth: 0, maxWidth: { sm: 180 } } : { maxWidth: 180 }}
      />
      <TextField
        size="small"
        type="date"
        label={t('common.to')}
        InputLabelProps={{ shrink: true }}
        value={value.dateTo}
        onChange={(e) => set({ dateTo: e.target.value })}
        sx={compact ? { flex: '1 1 150px', minWidth: 0, maxWidth: { sm: 180 } } : { maxWidth: 180 }}
      />
    </>
  );
  const bulkRow = bulkSelectedCount > 0 ? (
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
  ) : null;

  if (compact) {
    const statusChips = statusOptions.length ? (
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip
          label={t('common.all')}
          color={value.status === '' ? 'primary' : 'default'}
          variant={value.status === '' ? 'filled' : 'outlined'}
          onClick={() => set({ status: '' })}
        />
        {statusOptions.map((opt) => (
          <Chip
            key={opt.value}
            label={opt.label}
            color={value.status === opt.value ? 'primary' : 'default'}
            variant={value.status === opt.value ? 'filled' : 'outlined'}
            onClick={() => set({ status: value.status === opt.value ? '' : opt.value })}
          />
        ))}
      </Stack>
    ) : <span />;
    return (
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
          {statusChips}
          {actions}
        </Stack>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'flex-start' }}>
          {searchField}
          {dateRangePresets && showDateRange && dateControl === 'preset' ? dateSelect : null}
          {party ? (
            <Box sx={{ flex: '1 1 220px', minWidth: 0, maxWidth: { sm: 300 }, '& .MuiAutocomplete-root': { width: '100%', maxWidth: 'none' } }}>
              {party}
            </Box>
          ) : null}
          {controls ? <Box sx={{ flex: '0 1 180px', minWidth: 0, '& .MuiTextField-root': { width: '100%', minWidth: 0 } }}>{controls}</Box> : null}
          {showDateRange && showDateFields ? dateFields : null}
        </Box>
        {footer}
        {bulkRow}
      </Stack>
    );
  }

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
      {dateRangePresets && showDateRange && dateControl === 'chips' ? (
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
      {dateRangePresets && showDateRange && dateControl === 'preset' ? (
        <TextField
          select
          size="small"
          label={t('history.dateRange')}
          value={presetValue}
          onChange={(event) => applyPreset(event.target.value as DateRangePresetId | '')}
          sx={{ maxWidth: 280 }}
        >
          <MenuItem value="">{t('common.all')}</MenuItem>
          {DATE_RANGE_PRESET_IDS.map((id) => (
            <MenuItem key={id} value={id}>
              {t(`history.preset.${id}`)}
            </MenuItem>
          ))}
        </TextField>
      ) : null}
      {party}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} useFlexGap>
        <TextField
          size="small"
          label={searchLabel}
          placeholder={searchPlaceholder ?? t('common.search')}
          value={value.q}
          onChange={(e) => set({ q: e.target.value })}
          sx={{ minWidth: 220, flex: 1, maxWidth: 360 }}
          inputProps={searchLabel ? { 'aria-label': searchLabel } : undefined}
        />
        {showDateRange && showDateFields ? (
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
