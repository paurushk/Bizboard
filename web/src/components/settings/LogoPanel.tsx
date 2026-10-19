import { useEffect, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQueryClient } from '@tanstack/react-query';
import { deleteFileAsset, downloadFileAsset, updateCompany, uploadCompanyLogo } from '@/api/resources';
import { t } from '@/i18n';
import { confirmAction } from '@/utils/confirmBridge';
import { settingsErrorText } from '@/utils/settingsErrors';

const MAX_BYTES = 5 * 1024 * 1024;
const ACCEPTED = ['image/png', 'image/jpeg', 'image/webp'];

/**
 * SET-17: the logo printed on invoices. Upload, replace and remove act at once (they are not part
 * of the Save form): the image is stored first, then the company is pointed at it.
 */
export function LogoPanel({ logoId }: { logoId: number | null | undefined }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [currentId, setCurrentId] = useState<number | null>(logoId ?? null);
  const [loaded, setLoaded] = useState<{ id: number; url: string } | null>(null);
  const preview = loaded && loaded.id === currentId ? loaded.url : null;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    if (currentId) {
      downloadFileAsset(currentId)
        .then((blob) => {
          if (cancelled) return;
          url = URL.createObjectURL(blob);
          setLoaded({ id: currentId, url });
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [currentId]);

  const choose = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (!ACCEPTED.includes(file.type)) {
      setError(t('logoPanel.badType'));
      return;
    }
    if (file.size > MAX_BYTES) {
      setError(t('logoPanel.tooBig'));
      return;
    }
    setBusy(true);
    try {
      const id = await uploadCompanyLogo(file);
      await updateCompany({ logo: id } as never);
      const previous = currentId;
      setCurrentId(id);
      if (previous) void deleteFileAsset(previous).catch(() => undefined);
      await qc.invalidateQueries({ queryKey: ['company'] });
    } catch (e) {
      setError(settingsErrorText(e));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  const remove = async () => {
    if (!currentId || !(await confirmAction(t('logoPanel.removeConfirm')))) return;
    setBusy(true);
    setError(null);
    try {
      await updateCompany({ logo: null } as never);
      void deleteFileAsset(currentId).catch(() => undefined);
      setCurrentId(null);
      await qc.invalidateQueries({ queryKey: ['company'] });
    } catch (e) {
      setError(settingsErrorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={1.5}>
      <Typography variant="h6" component="h2" fontWeight={600}>
        {t('logoPanel.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {t('logoPanel.help')}
      </Typography>
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Stack direction="row" spacing={2} alignItems="center">
        <Box sx={{ width: 96, height: 96, border: 1, borderColor: 'divider', borderRadius: 1, display: 'grid', placeItems: 'center', overflow: 'hidden' }}>
          {preview ? (
            <img src={preview} alt={t('logoPanel.alt')} style={{ maxWidth: '100%', maxHeight: '100%' }} />
          ) : (
            <Typography variant="caption" color="text.secondary">
              {currentId ? t('logoPanel.loading') : t('logoPanel.none')}
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" size="small" disabled={busy} onClick={() => input.current?.click()}>
            {currentId ? t('logoPanel.replace') : t('logoPanel.upload')}
          </Button>
          {currentId ? (
            <Button size="small" color="error" disabled={busy} onClick={() => void remove()}>
              {t('logoPanel.remove')}
            </Button>
          ) : null}
        </Stack>
        <input
          ref={input}
          type="file"
          accept={ACCEPTED.join(',')}
          hidden
          aria-label={t('logoPanel.upload')}
          onChange={(e) => void choose(e.target.files?.[0])}
        />
      </Stack>
    </Stack>
  );
}
