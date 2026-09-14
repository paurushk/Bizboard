import Chip from '@mui/material/Chip';
import { t } from '@/i18n';

/** Visible when collection_status is stop_credit or overdue_severe (G-23). */
export function CreditHoldChip() {
  return <Chip size="small" color="error" label={t('phase1.creditHoldChip')} />;
}
