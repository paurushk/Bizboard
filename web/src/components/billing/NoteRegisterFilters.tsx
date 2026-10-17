import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import type { NoteRegisterState } from '@/hooks/useNoteRegisterFilters';
import { t } from '@/i18n';

const STATUSES = ['DRAFT', 'COMPLETED', 'CANCELLED'] as const;

export function NoteRegisterFilterBar({
  state,
  rangeInvalid,
  onChange,
  onExport,
  exporting,
  canExport,
}: {
  state: NoteRegisterState;
  rangeInvalid: boolean;
  onChange: (patch: Partial<NoteRegisterState>) => void;
  onExport: () => void;
  exporting: boolean;
  canExport: boolean;
}) {
  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }} flexWrap="wrap" useFlexGap>
      <TextField
        size="small"
        label={t('common.search')}
        placeholder={t('phase1.searchNotes')}
        value={state.search}
        onChange={(e) => onChange({ search: e.target.value })}
        sx={{ minWidth: { sm: 260 } }}
      />
      <TextField
        select
        size="small"
        label={t('common.status')}
        value={state.status}
        onChange={(e) => onChange({ status: e.target.value })}
        sx={{ minWidth: 150 }}
      >
        <MenuItem value="">{t('common.all')}</MenuItem>
        {STATUSES.map((s) => (
          <MenuItem key={s} value={s}>
            {t(`status.${s}`)}
          </MenuItem>
        ))}
      </TextField>
      <TextField
        type="date"
        size="small"
        label={t('common.from')}
        value={state.dateFrom}
        onChange={(e) => onChange({ dateFrom: e.target.value })}
        InputLabelProps={{ shrink: true }}
        error={rangeInvalid}
      />
      <TextField
        type="date"
        size="small"
        label={t('common.to')}
        value={state.dateTo}
        onChange={(e) => onChange({ dateTo: e.target.value })}
        InputLabelProps={{ shrink: true }}
        error={rangeInvalid}
        helperText={rangeInvalid ? t('phase1.dateRangeInvalid') : undefined}
      />
      {canExport ? (
        <Button variant="outlined" size="small" disabled={exporting || rangeInvalid} onClick={onExport}>
          {t('phase1.exportRegister')}
        </Button>
      ) : null}
    </Stack>
  );
}
