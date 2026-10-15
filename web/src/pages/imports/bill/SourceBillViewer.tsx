import { useEffect, useRef, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import Link from '@mui/material/Link';
import RotateRightIcon from '@mui/icons-material/RotateRight';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import { fetchImportSourceFile } from '@/api/resources';
import { t } from '@/i18n';

/**
 * The uploaded bill beside the extracted rows, so each row can be checked
 * against the print without switching windows. Fetched with the user's auth
 * (a plain <img src> cannot send it) and works after a refresh because it does
 * not depend on the local File object.
 */
/** Mount with `key={jobId}` so a different job starts from a clean state. */
export function SourceBillViewer({
  jobId,
  highlight,
}: {
  jobId: number;
  /** [x, y, width, height] as 0-1 fractions of the image; drawn over the row being looked at. */
  highlight?: number[] | null;
}) {
  const [source, setSource] = useState<{ url: string; contentType: string } | null>(null);
  const [failed, setFailed] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [turns, setTurns] = useState(0);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    let created: string | null = null;
    fetchImportSourceFile(jobId)
      .then((result) => {
        if (cancelled) {
          URL.revokeObjectURL(result.url);
          return;
        }
        created = result.url;
        setSource(result);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [jobId]);

  const isPdf = source?.contentType === 'application/pdf';

  return (
    <Paper variant="outlined" sx={{ p: 1, position: { lg: 'sticky' }, top: { lg: 72 } }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="subtitle2">{t('billUpload.sourceTitle')}</Typography>
        {!isPdf ? (
          <Stack direction="row">
            <IconButton
              size="small"
              aria-label={t('billUpload.sourceRotate')}
              onClick={() => setTurns((n) => (n + 1) % 4)}
            >
              <RotateRightIcon fontSize="small" />
            </IconButton>
            <IconButton
              size="small"
              aria-label={t('billUpload.zoomOut')}
              onClick={() => setZoom((z) => Math.max(0.5, Math.round((z - 0.25) * 100) / 100))}
            >
              <ZoomOutIcon fontSize="small" />
            </IconButton>
            <IconButton
              size="small"
              aria-label={t('billUpload.zoomIn')}
              onClick={() => setZoom((z) => Math.min(4, Math.round((z + 0.25) * 100) / 100))}
            >
              <ZoomInIcon fontSize="small" />
            </IconButton>
          </Stack>
        ) : null}
      </Stack>
      {failed ? <Alert severity="info">{t('billUpload.sourceUnavailable')}</Alert> : null}
      {!source && !failed ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={24} aria-label={t('common.loading')} />
        </Box>
      ) : null}
      {source && isPdf ? (
        <>
          <Box
            component="object"
            data={source.url}
            type="application/pdf"
            aria-label={t('billUpload.sourceTitle')}
            sx={{ width: '100%', height: { xs: 360, lg: '70vh' }, border: 0 }}
          >
            {/* Shown by browsers and phones that cannot display a PDF inline. */}
            <Link href={source.url} target="_blank" rel="noopener noreferrer">
              {t('billUpload.sourceOpenPdf')}
            </Link>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
            {t('billUpload.sourcePdfNoZoom')}{' '}
            <Link href={source.url} target="_blank" rel="noopener noreferrer">
              {t('billUpload.sourceOpenPdf')}
            </Link>
          </Typography>
        </>
      ) : null}
      {source && !isPdf ? (
        <Box
          data-testid="bill-pan-area"
          sx={{ overflow: 'auto', maxHeight: { xs: 360, lg: '70vh' }, cursor: zoom > 1 ? 'grab' : 'default', touchAction: 'pan-y' }}
          // Drag to pan when zoomed in (scrollbars still work).
          onPointerDown={(e) => {
            if (zoom <= 1) return;
            const el = e.currentTarget;
            drag.current = { x: e.clientX, y: e.clientY, left: el.scrollLeft, top: el.scrollTop };
            el.setPointerCapture?.(e.pointerId);
          }}
          onPointerMove={(e) => {
            const start = drag.current;
            if (!start) return;
            e.currentTarget.scrollLeft = start.left - (e.clientX - start.x);
            e.currentTarget.scrollTop = start.top - (e.clientY - start.y);
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
        >
          <Box sx={{ position: 'relative', width: `${zoom * 100}%` }}>
            <Box
              component="img"
              src={source.url}
              alt={t('billUpload.sourceTitle')}
              draggable={false}
              sx={{ width: '100%', display: 'block', transform: `rotate(${turns * 90}deg)`, transformOrigin: 'center' }}
            />
            {highlight && highlight.length === 4 ? (
              <Box
                data-testid="bill-row-highlight"
                aria-hidden
                sx={{
                  position: 'absolute',
                  left: `${highlight[0] * 100}%`,
                  top: `${highlight[1] * 100}%`,
                  width: `${highlight[2] * 100}%`,
                  height: `${highlight[3] * 100}%`,
                  border: '2px solid',
                  borderColor: 'warning.main',
                  bgcolor: 'rgba(255, 193, 7, 0.18)',
                  pointerEvents: 'none',
                }}
              />
            ) : null}
          </Box>
        </Box>
      ) : null}
    </Paper>
  );
}
