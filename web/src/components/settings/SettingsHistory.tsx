import { useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getSettingsHistory, type SettingsHistoryItem } from '@/api/resources';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { t } from '@/i18n';

function shown(value: unknown): string {
  if (value === null || value === undefined || value === '') return t('settingsHistory.empty');
  if (typeof value === 'boolean') return value ? t('settingsHistory.on') : t('settingsHistory.off');
  return String(value);
}

function fieldLabel(field: string): string {
  return field.replace(/_/g, ' ');
}

function Row({ item }: { item: SettingsHistoryItem }) {
  return (
    <Box component="li" sx={{ py: 1.25, borderBottom: 1, borderColor: 'divider', listStyle: 'none' }}>
      <Typography variant="body2" fontWeight={600}>
        {item.who || t('settingsHistory.system')}
        {item.what ? ` · ${item.what}` : ''}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {new Date(item.at).toLocaleString()} · {t(`settingsHistory.action.${item.action}`)}
      </Typography>
      {item.changes.map((c) => (
        <Typography key={c.field} variant="body2" sx={{ mt: 0.25 }}>
          {fieldLabel(c.field)}:{' '}
          {c.changed ? t('settingsHistory.changedHidden') : `${shown(c.from)} → ${shown(c.to)}`}
        </Typography>
      ))}
    </Box>
  );
}

/** SET-21: a button and drawer listing who changed what on this screen, newest first. */
export function SettingsHistory({ area }: { area: string }) {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ['settings-history', area],
    queryFn: () => getSettingsHistory(area),
    enabled: open,
  });
  return (
    <>
      <Button size="small" variant="text" onClick={() => setOpen(true)}>
        {t('settingsHistory.open')}
      </Button>
      <Drawer anchor="right" open={open} onClose={() => setOpen(false)} PaperProps={{ sx: { width: { xs: '100%', sm: 420 }, p: 2 } }}>
        <Stack spacing={1.5} role="dialog" aria-label={t('settingsHistory.title')}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6">{t('settingsHistory.title')}</Typography>
            <IconButton aria-label={t('common.close')} onClick={() => setOpen(false)}>
              ×
            </IconButton>
          </Stack>
          <AsyncSection
            query={query}
            isEmpty={(data) => data.items.length === 0}
            empty={{ description: t('settingsHistory.none') }}
          >
            {(data) => (
              <Box component="ul" sx={{ m: 0, p: 0 }}>
                {data.items.map((item) => (
                  <Row key={item.id} item={item} />
                ))}
              </Box>
            )}
          </AsyncSection>
        </Stack>
      </Drawer>
    </>
  );
}
