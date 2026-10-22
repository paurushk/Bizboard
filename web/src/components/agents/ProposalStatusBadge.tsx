import Chip from '@mui/material/Chip';
import type { ProposalStatus } from '@/api/agents';
import { t } from '@/i18n';

const COLORS: Record<ProposalStatus, 'default' | 'success' | 'warning' | 'error' | 'info'> = {
  PENDING: 'info',
  APPROVED: 'info',
  EXECUTED: 'success',
  FAILED: 'error',
  REJECTED: 'default',
  CANCELLED: 'default',
  EXPIRED: 'warning',
};

export function ProposalStatusBadge({ status }: { status: ProposalStatus }) {
  return <Chip size="small" color={COLORS[status] ?? 'default'} label={t(`agents.status.${status}`)} />;
}
