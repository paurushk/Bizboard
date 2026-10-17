import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { t } from '@/i18n';
import { MONEY_VIA } from '@/lib/moneyLinks';

/** True when the page was opened from a Money hub tile (`?via=money`). */
function useOpenedFromMoney(): boolean {
  const [params] = useSearchParams();
  return params.get('via') === MONEY_VIA;
}

type Props = {
  /** What the hub filtered this page to, in words ("Overdue bills"). */
  filterLabel: string;
  /** Drop the hub's filter and show the whole list. The bar goes away with it. */
  onShowAll: () => void;
};

/**
 * "Opened from Money" strip: says which slice of the list this is and gives the way back.
 * Renders nothing unless the page was reached from the hub.
 */
export function MoneyHandoffBar({ filterLabel, onShowAll }: Props) {
  const fromMoney = useOpenedFromMoney();
  if (!fromMoney) return null;
  return (
    <Alert
      severity="info"
      variant="outlined"
      icon={false}
      role="status"
      action={
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={onShowAll}>
            {t('money.handoff.showAll')}
          </Button>
          <Button size="small" component={RouterLink} to="/money">
            {t('money.handoff.back')}
          </Button>
        </Stack>
      }
    >
      {t('money.handoff.from', { filter: filterLabel })}
    </Alert>
  );
}
