import Button from '@mui/material/Button';
import { Link as RouterLink } from 'react-router-dom';
import { EmptyState } from '@/components/PageState';
import { t } from '@/i18n';

export function ForbiddenPage() {
  return (
    <EmptyState
      title={t('landing.forbiddenTitle')}
      description={t('landing.forbiddenDescription')}
      action={
        <Button component={RouterLink} to="/" variant="contained">
          {t('landing.backHome')}
        </Button>
      }
    />
  );
}
