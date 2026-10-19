import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Typography from '@mui/material/Typography';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { t } from '@/i18n';
import { HISTORY_AREAS, nextSettingsStep, settingsDefForPath } from '@/navigation/settingsAccess';
import { SCREEN_IMPACT } from '@/navigation/settingsImpact';
import { SettingsHistory } from '@/components/settings/SettingsHistory';
import { onSettingsWrite } from '@/utils/settingsSaveSignal';

/**
 * SET-19: the frame around every Settings screen. A way back to the overview, and, after something
 * was saved, the next screen in the usual set-up order. Leaving with unsaved changes is already
 * guarded by each screen's own leave guard, so Back never loses edits without asking.
 */
export function SettingsContinuity() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [savedOn, setSavedOn] = useState<string | null>(null);

  useEffect(() => onSettingsWrite(() => setSavedOn(window.location.pathname)), []);

  const screen = settingsDefForPath(pathname);
  if (!screen) return null;
  const historyArea = HISTORY_AREAS[screen.id];
  const next = savedOn === pathname ? nextSettingsStep(pathname, user) : null;

  return (
    <Stack spacing={1} sx={{ mb: 1 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Link component={RouterLink} to="/settings" variant="body2" underline="hover">
          {t('settingsContinuity.back')}
        </Link>
        {historyArea && user?.role === 'OWNER' ? <SettingsHistory area={historyArea} /> : null}
      </Stack>
      {(SCREEN_IMPACT[screen.id] ?? []).length > 0 ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap aria-label={t('settingsShell.usedBy')}>
          <Typography variant="caption" color="text.secondary">
            {t('settingsShell.usedBy')}
          </Typography>
          {SCREEN_IMPACT[screen.id].map((key) => (
            <Chip key={key} size="small" variant="outlined" label={t(key)} />
          ))}
        </Stack>
      ) : null}
      {savedOn === pathname ? (
        <Alert
          severity="success"
          // A custom action replaces the Alert's own close button, so Dismiss is spelled out.
          action={
            <Stack direction="row" spacing={0.5}>
              {next ? (
                <Button component={RouterLink} to={next.path} color="inherit" size="small">
                  {t('settingsContinuity.goNext', { name: t(next.labelKey) })}
                </Button>
              ) : (
                <Button component={RouterLink} to="/settings" color="inherit" size="small">
                  {t('settingsContinuity.backToOverview')}
                </Button>
              )}
              <Button color="inherit" size="small" onClick={() => setSavedOn(null)}>
                {t('common.close')}
              </Button>
            </Stack>
          }
        >
          {next ? t('settingsContinuity.savedNext', { name: t(next.labelKey) }) : t('settingsContinuity.saved')}
        </Alert>
      ) : null}
    </Stack>
  );
}
