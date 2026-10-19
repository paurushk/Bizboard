import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { listGstSnapshots } from '@/api/resources';
import { t } from '@/i18n';
import { DataTable } from '@/pages/phase/phaseShared';

/** The months saved with "Save snapshot", newest first, so a saved month can be found again. */
export function GstSnapshotList({ kind }: { kind: 'gstr1' | 'gstr3b' }) {
  const query = useQuery({ queryKey: ['gst-snapshots', kind], queryFn: () => listGstSnapshots(kind) });
  const rows = (query.data ?? []).map((r) => ({ ...r }));
  return (
    <Accordion disableGutters variant="outlined">
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography fontWeight={600}>
          {t('gstr1.savedSnapshots')}{query.isSuccess ? ` · ${rows.length}` : ''}
        </Typography>
      </AccordionSummary>
      <AccordionDetails>
        {query.isError ? (
          <Typography color="error">{getErrorMessage(query.error)}</Typography>
        ) : (
          <DataTable
            rows={rows}
            empty={t('gstr1.noSnapshots')}
            columns={[
              { key: 'period', label: t('reports.period') },
              { key: 'generatedAt', label: t('gstr1.savedOn'), render: (r) => String(r.generatedAt ?? '').replace('T', ' ').slice(0, 16) },
              { key: 'generatedBy', label: t('gstr1.savedBy') },
              { key: 'builderVersion', label: t('gstr1.version') },
              { key: 'contentHash', label: t('gstr1.fingerprint') },
            ]}
          />
        )}
      </AccordionDetails>
    </Accordion>
  );
}
