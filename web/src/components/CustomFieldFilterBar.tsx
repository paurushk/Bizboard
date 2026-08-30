import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Popover from '@mui/material/Popover';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import FilterListOutlinedIcon from '@mui/icons-material/FilterListOutlined';
import { useState } from 'react';
import { isItemCustomFieldsV2Enabled } from '@/config/features';
import { t } from '@/i18n';
import type { ItemCustomFieldDef } from '@/types/domain';
import { type CfFilterMap } from '@/hooks/useCfFilters';

interface Props {
  defs: ItemCustomFieldDef[];
  value: CfFilterMap;
  onChange: (next: CfFilterMap) => void;
  compact?: boolean;
}

export function CustomFieldFilterBar({ defs, value, onChange, compact }: Props) {
  const listDefs = isItemCustomFieldsV2Enabled()
    ? defs.filter((row) => row.active !== false && row.type === 'list' && row.key)
    : [];
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const selectedCount = Object.values(value).reduce((sum, items) => sum + items.length, 0);

  if (!listDefs.length) return null;

  const controls = listDefs.map((def) => {
    const options = Array.from(new Set([...(def.options ?? []), ...(value[def.key] ?? [])]));
    return (
      <Autocomplete
        key={def.key}
        multiple
        size="small"
        options={options}
        value={value[def.key] ?? []}
        onChange={(_, next) => {
          const updated = { ...value };
          if (next.length) updated[def.key] = next;
          else delete updated[def.key];
          onChange(updated);
        }}
        renderTags={(selected, getTagProps) =>
          selected.map((option, index) => <Chip size="small" label={option} {...getTagProps({ index })} />)
        }
        renderInput={(params) => (
          <TextField {...params} label={def.label} placeholder={t('customFields.all')} />
        )}
        sx={{ minWidth: compact ? 160 : 200, flex: compact ? '0 1 200px' : 1 }}
      />
    );
  });

  const collapse = listDefs.length > 2 || compact;

  if (collapse) {
    return (
      <>
        <Button
          size="small"
          variant={selectedCount ? 'contained' : 'outlined'}
          startIcon={<FilterListOutlinedIcon />}
          onClick={(e) => setAnchor(e.currentTarget)}
        >
          {t('customFields.filters')}
          {selectedCount ? ` (${selectedCount})` : ''}
        </Button>
        <Popover
          open={Boolean(anchor)}
          anchorEl={anchor}
          onClose={() => setAnchor(null)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        >
          <Stack spacing={1.5} sx={{ p: 2, minWidth: 280 }}>
            {controls}
          </Stack>
        </Popover>
      </>
    );
  }

  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {controls}
    </Stack>
  );
}
