import Autocomplete from '@mui/material/Autocomplete';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { SxProps, Theme } from '@mui/material/styles';
import { t } from '@/i18n';

export type PartyOption = {
  id: number;
  name: string;
  phone?: string;
  gstin?: string;
  state?: string;
  billingAddress?: string;
  address?: string;
  creditDays?: number;
};

export function PartySelectPanel<T extends PartyOption>({
  label,
  selectedParty,
  editingStatus,
  onClear,
  options,
  query,
  onQueryChange,
  onSelect,
  loading,
  onCreatePartyClick,
  onEditPartyClick,
  onQuickCashClick,
  quickCashLabel = t('billing.walkInCustomerBtn'),
  sx,
}: {
  label: string;
  selectedParty: T | null | undefined;
  editingStatus: string | null;
  onClear: () => void;
  options: T[];
  query: string;
  onQueryChange: (value: string) => void;
  onSelect: (party: T | null) => void;
  loading?: boolean;
  onCreatePartyClick: () => void;
  onEditPartyClick?: () => void;
  onQuickCashClick?: () => void;
  quickCashLabel?: string;
  sx?: SxProps<Theme>;
}) {
  const address = selectedParty?.billingAddress ?? selectedParty?.address;
  return (
    <Box
      sx={[
        {
          flex: 1.2,
          border: '1px dashed',
          borderColor: 'primary.light',
          borderRadius: 1,
          p: 2,
          minHeight: 120,
        },
        ...(sx ? (Array.isArray(sx) ? sx : [sx]) : []),
      ]}
    >
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      {selectedParty ? (
        <Stack spacing={0.5} sx={{ mt: 0.5 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
            <Box>
              <Typography fontWeight={700}>{selectedParty.name}</Typography>
              {selectedParty.phone ? (
                <Typography variant="body2" color="text.secondary">
                  {selectedParty.phone}
                </Typography>
              ) : null}
              {selectedParty.gstin ? (
                <Typography variant="body2" color="text.secondary">
                  GSTIN: {selectedParty.gstin}
                </Typography>
              ) : null}
              {selectedParty.state ? (
                <Typography variant="body2" color="text.secondary">
                  {t('auth.state')}: {selectedParty.state}
                </Typography>
              ) : null}
              {address ? (
                <Typography variant="body2" color="text.secondary">
                  {address}
                </Typography>
              ) : null}
            </Box>
            {editingStatus !== 'COMPLETED' ? (
              <Stack direction="row" spacing={0.5}>
                {onEditPartyClick ? (
                  <Button size="small" onClick={onEditPartyClick}>
                    {t('common.edit')}
                  </Button>
                ) : null}
                <Button size="small" onClick={onClear}>
                  Change
                </Button>
              </Stack>
            ) : null}
          </Stack>
          {!selectedParty.state && !selectedParty.gstin && onEditPartyClick && editingStatus !== 'COMPLETED' ? (
            <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 0.5 }}>
              ⚠️ State & GSTIN not set.{' '}
              <Link component="button" type="button" variant="caption" onClick={onEditPartyClick}>
                Add State / GSTIN
              </Link>
            </Typography>
          ) : null}
        </Stack>
      ) : (
        <Stack spacing={1} sx={{ mt: 1 }}>
          <Autocomplete<T>
            options={options}
            getOptionLabel={(o) => (o.phone ? `${o.name} (${o.phone})` : o.name)}
            filterOptions={(opts) => opts}
            inputValue={query}
            onInputChange={(_, v, reason) => {
              if (reason === 'input' || reason === 'clear') onQueryChange(v);
            }}
            value={null}
            onChange={(_, v) => onSelect(v)}
            loading={loading}
            renderInput={(params) => (
              <TextField
                {...params}
                label={label}
                placeholder="Search by customer name, phone, or GSTIN…"
                helperText={
                  query.trim().length > 0 && query.trim().length < 2
                    ? 'Type name or phone number'
                    : undefined
                }
              />
            )}
          />
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
            <Link component="button" type="button" underline="hover" onClick={onCreatePartyClick}>
              + {t('billing.createParty')}
            </Link>
            {onQuickCashClick ? (
              <Button size="small" variant="outlined" color="primary" onClick={onQuickCashClick}>
                {quickCashLabel}
              </Button>
            ) : null}
          </Stack>
        </Stack>
      )}
    </Box>
  );
}
