import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import { Link as RouterLink } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState } from '@/components/PageState';
import { t } from '@/i18n';

export function ForbiddenPage() {
  const { user } = useAuth();
  const isSalesStaff = user?.role === 'SALES_STAFF';
  const homeTarget = isSalesStaff ? '/pos' : '/';

  return (
    <EmptyState
      title={t('landing.forbiddenTitle')}
      description={t('landing.forbiddenDescription')}
      action={
        <Stack direction="row" spacing={2} justifyContent="center">
          <Button component={RouterLink} to={homeTarget} variant="contained">
            {isSalesStaff ? t('nav.pos') : t('landing.backHome')}
          </Button>
          {isSalesStaff ? (
            <Button component={RouterLink} to="/sales/history" variant="outlined">
              {t('nav.salesHistory')}
            </Button>
          ) : null}
        </Stack>
      }
    />
  );
}
