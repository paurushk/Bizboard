import Paper from '@mui/material/Paper';
import { useQuery } from '@tanstack/react-query';
import { recordLinks } from '@/api/care';
import { isComplaintsEnabled, isContractsEnabled, isProjectsEnabled, isSupportTicketsEnabled, isWorkshopEnabled } from '@/config/features';
import { LinkedRecords } from './kit';

function careEnabled() {
  return isSupportTicketsEnabled() || isComplaintsEnabled() || isContractsEnabled() || isWorkshopEnabled() || isProjectsEnabled();
}

/**
 * Tickets, complaints, jobs, contracts and projects tied to a customer or an invoice (XLK-03/04).
 * An invoice shows the panel only when something is linked, so ordinary invoices stay quiet.
 */
export function CareLinksPanel({ entity, id, always = false }: { entity: 'customer' | 'invoice'; id: number; always?: boolean }) {
  const enabled = careEnabled();
  const links = useQuery({
    queryKey: ['care-links', entity, id],
    queryFn: () => recordLinks(entity, id),
    enabled: enabled && id > 0,
  });
  if (!enabled) return null;
  if (!always && (links.isLoading || links.isError || (links.data ?? []).length === 0)) return null;
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <LinkedRecords entity={entity} id={id} />
    </Paper>
  );
}
