import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useNavigate } from 'react-router-dom';
import { t } from '@/i18n';
import type { SourceQuotation } from '@/types/domain';
import { statusLabelKey } from '@/utils/status';

/** Which quotation(s) a sales order or invoice was converted from, with who sold it. */
export function SourceQuotationsPanel({
  sources,
  differ = false,
}: {
  sources?: SourceQuotation[];
  /** True when the source quotations disagree on salesperson, channel or address. */
  differ?: boolean;
}) {
  const navigate = useNavigate();
  if (!sources || sources.length === 0) return null;
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} aria-label={t('phase1.quotationSourcePanel')}>
      <Typography variant="subtitle2" gutterBottom>
        {t('phase1.quotationSourcePanel')}
      </Typography>
      <Stack spacing={0.5}>
        {sources.map((source) => (
          <Stack key={source.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Button size="small" variant="text" onClick={() => void navigate(`/sales/quotations/${source.id}`)}>
              {source.number || `#${source.id}`}
            </Button>
            <Typography variant="body2" color="text.secondary">
              {t(statusLabelKey(source.status))}
              {source.salesmanName ? ` · ${source.salesmanName}` : ''}
              {source.salesChannel ? ` · ${source.salesChannel}` : ''}
            </Typography>
          </Stack>
        ))}
      </Stack>
      {differ ? (
        <Alert severity="info" sx={{ mt: 1 }}>
          {t('phase1.quotationDifferNote')}
        </Alert>
      ) : null}
    </Paper>
  );
}
