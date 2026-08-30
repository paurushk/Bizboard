import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Popover from '@mui/material/Popover';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import ViewColumnOutlinedIcon from '@mui/icons-material/ViewColumnOutlined';
import { useState } from 'react';
import { t } from '@/i18n';
import type { ColumnSpec } from '@/hooks/useColumnPrefs';

interface Props {
  columns: ColumnSpec[];
  isVisible: (id: string) => boolean;
  toggle: (id: string) => void;
  reset: () => void;
}

export function ColumnPicker({ columns, isVisible, toggle, reset }: Props) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const standard = columns.filter((col) => col.group === 'standard');
  const custom = columns.filter((col) => col.group === 'custom');

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        startIcon={<ViewColumnOutlinedIcon />}
        onClick={(e) => setAnchor(e.currentTarget)}
      >
        {t('customFields.columns')}
      </Button>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Stack spacing={1} sx={{ p: 2, minWidth: 240 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="subtitle2">{t('customFields.columns')}</Typography>
            <Button size="small" onClick={reset}>
              {t('customFields.resetColumns')}
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {t('customFields.standard')}
          </Typography>
          {standard.map((col) => (
            <FormControlLabel
              key={col.id}
              control={
                <Checkbox
                  size="small"
                  checked={isVisible(col.id)}
                  disabled={col.removable === false}
                  onChange={() => toggle(col.id)}
                />
              }
              label={col.label}
            />
          ))}
          {custom.length ? (
            <>
              <Divider />
              <Typography variant="caption" color="text.secondary">
                {t('customFields.customGroup')}
              </Typography>
              {custom.map((col) => (
                <FormControlLabel
                  key={col.id}
                  control={
                    <Checkbox size="small" checked={isVisible(col.id)} onChange={() => toggle(col.id)} />
                  }
                  label={col.label}
                />
              ))}
            </>
          ) : null}
        </Stack>
      </Popover>
    </>
  );
}
