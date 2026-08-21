import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState } from '@/components/PageState';
import { t } from '@/i18n';
import { filterNav, findFirstNavPath, isReallyReachable } from '@/navigation/menu';

export function LimitedAccessLanding() {
  const { user } = useAuth();
  const location = useLocation();
  const [showWelcome, setShowWelcome] = useState(false);
  const firstPath = findFirstNavPath(user);
  const nav = filterNav(user);
  const links = nav
    .flatMap((section) => {
      if (section.path) return [{ labelKey: section.labelKey, path: section.path }];
      return (section.children ?? [])
        .filter((c) => c.path)
        .map((c) => ({ labelKey: c.labelKey, path: c.path! }));
    })
    .filter((link) => isReallyReachable(user, link.path));

  useEffect(() => {
    if (localStorage.getItem('bb_role_welcome') === '1') {
      setShowWelcome(true);
      localStorage.removeItem('bb_role_welcome');
    }
  }, []);

  return (
    <Stack spacing={3} sx={{ py: 4, px: 2, alignItems: 'center' }}>
      {showWelcome ? (
        <Alert severity="success" sx={{ maxWidth: 600, width: '100%' }}>
          {t('landing.roleWelcome')}
        </Alert>
      ) : null}
      {links.length === 0 && location.pathname !== '/' ? (
        <Alert severity="warning" sx={{ maxWidth: 600, width: '100%' }}>
          <strong>{t('landing.forbiddenTitle')}:</strong> {t('landing.forbiddenDescription')}
        </Alert>
      ) : null}
      <EmptyState
        title={t('landing.limitedTitle')}
        description={t('landing.limitedDescription')}
        action={
          firstPath ? (
            <Button component={RouterLink} to={firstPath} variant="contained">
              {t('landing.goToWorkspace')}
            </Button>
          ) : null
        }
      />
      {links.length > 0 ? (
        <Stack spacing={1} alignItems="center">
          <Typography variant="subtitle2" color="text.secondary">
            {t('landing.availableAreas')}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap justifyContent="center">
            {links.slice(0, 6).map((link) => (
              <Button key={link.path} component={RouterLink} to={link.path} size="small" variant="outlined">
                {t(link.labelKey)}
              </Button>
            ))}
          </Stack>
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary" textAlign="center">
          {t('landing.contactOwner')}
        </Typography>
      )}
    </Stack>
  );
}
