import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Badge from '@mui/material/Badge';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getWhatsNewSeen, listAnnouncements, markWhatsNewSeen } from '@/api/announcements';
import { WHATS_NEW, newestWhatsNewId } from '@/help/whatsNew';
import { getLocale, t } from '@/i18n';

/** WP-CM3: "What's new" in the top bar, with a dot until the newest entry is opened. */
export function WhatsNewButton() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const seen = useQuery({ queryKey: ['whats-new-seen'], queryFn: getWhatsNewSeen, staleTime: 10 * 60_000, retry: false });
  const newest = newestWhatsNewId();
  const unread = Boolean(newest) && seen.isSuccess && (seen.data ?? '') < newest;
  const mark = useMutation({
    mutationFn: () => markWhatsNewSeen(newest),
    onSuccess: (value) => qc.setQueryData(['whats-new-seen'], value),
  });
  const hindi = getLocale() === 'hi';
  return (
    <>
      <Badge color="secondary" variant="dot" invisible={!unread} overlap="rectangular">
        <Button
          color="inherit"
          size="small"
          onClick={() => {
            setOpen(true);
            if (unread) mark.mutate();
          }}
        >
          {t('whatsNew.button')}
        </Button>
      </Badge>
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('whatsNew.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            {WHATS_NEW.map((entry) => {
              const copy = hindi ? entry.hi : entry.en;
              return (
                <Stack key={entry.id} spacing={0.5}>
                  <Typography fontWeight={600}>{copy.title}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {copy.body}
                  </Typography>
                </Stack>
              );
            })}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>{t('whatsNew.close')}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

/** WP-CM3: staff banners for maintenance or incidents, shown on every screen while live. */
export function AnnouncementBanners() {
  const rows = useQuery({ queryKey: ['announcements'], queryFn: listAnnouncements, staleTime: 5 * 60_000, retry: false });
  const hindi = getLocale() === 'hi';
  const list = Array.isArray(rows.data) ? rows.data : [];
  if (list.length === 0) return null;
  return (
    <Stack spacing={1} sx={{ mb: 2 }}>
      {list.map((row) => (
        <Alert key={row.id} severity={row.severity}>
          {hindi ? row.textHi : row.textEn}
        </Alert>
      ))}
    </Stack>
  );
}
