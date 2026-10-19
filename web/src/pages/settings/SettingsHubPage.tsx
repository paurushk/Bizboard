import Box from '@mui/material/Box';
import Card from '@mui/material/Card';
import CardActionArea from '@mui/material/CardActionArea';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getSettingsHealth, type SettingsHealthItem } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { t } from '@/i18n';
import { SETTINGS_GROUPS, SETTINGS_ROUTES } from '@/navigation/settingsAccess';
import { canManageUsers } from '@/utils/permissions';

/** One sentence the owner can act on, per checklist item and state. */
function healthDetail(item: SettingsHealthItem): string {
  if (item.id === 'licences') {
    if (item.expired) return t('settingsHub.licencesExpired', { count: item.expired });
    if (item.expiring) return t('settingsHub.licencesExpiring', { count: item.expiring });
    return item.count ? t('settingsHub.licencesOk', { count: item.count }) : t('settingsHub.licencesNone');
  }
  if (item.id === 'users') {
    if (item.expired) return t('settingsHub.usersExpired', { count: item.expired });
    if (item.pending) return t('settingsHub.usersPending', { count: item.pending });
    return t('settingsHub.usersOk');
  }
  if (item.id === 'backup') return t('settingsHub.backupFailed');
  if (item.id === 'webhook') return t('settingsHub.webhookQuiet');
  if (item.id === 'plan') return t('settingsHub.planClose');
  if (item.id === 'taxprofile') return t(`settingsHub.taxprofile.${item.status === 'ok' ? 'ok' : 'todo'}`);
  if (item.id === 'gateway' && item.status === 'warn') return t('settingsHub.gatewayUnverified');
  return t(`settingsHub.${item.id}.${item.status === 'ok' ? 'ok' : 'todo'}`);
}

function HealthPanel() {
  const query = useQuery({ queryKey: ['settings-health'], queryFn: getSettingsHealth });
  return (
    <Stack spacing={1} component="section" aria-labelledby="settings-health-title">
      <Typography id="settings-health-title" variant="h6">
        {t('settingsHub.healthTitle')}
      </Typography>
      <AsyncSection query={query}>
        {(data) => (
          <>
            <Typography variant="body2" color="text.secondary">
              {data.needsAttention === 0
                ? t('settingsHub.allGood')
                : t('settingsHub.needsAttention', { count: data.needsAttention })}
            </Typography>
            <Stack spacing={1}>
              {data.items.map((item) => (
                <Card key={item.id} variant="outlined">
                  <CardActionArea component={RouterLink} to={item.path}>
                    <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1.25 }}>
                      <Chip
                        size="small"
                        color={item.status === 'ok' ? 'success' : item.status === 'warn' ? 'warning' : 'default'}
                        label={item.status === 'ok' ? t('settingsHub.statusOk') : t('settingsHub.statusTodo')}
                      />
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="subtitle2">{t(`settingsHub.itemTitle.${item.id}`)}</Typography>
                        <Typography variant="body2" color="text.secondary">
                          {healthDetail(item)}
                        </Typography>
                      </Box>
                    </CardContent>
                  </CardActionArea>
                </Card>
              ))}
            </Stack>
          </>
        )}
      </AsyncSection>
    </Stack>
  );
}

export function SettingsHubPage() {
  const { user } = useAuth();
  const groups = SETTINGS_GROUPS.map((group) => ({
    ...group,
    screens: SETTINGS_ROUTES.filter((def) => def.group === group.id && def.menu(user)),
  })).filter((group) => group.screens.length > 0);

  return (
    <SettingsPage title={t('settingsHub.title')} purpose={t('settingsHub.purpose')}>
      {canManageUsers(user) ? <HealthPanel /> : null}
      {groups.map((group) => (
        <Stack key={group.id} spacing={1} component="section" aria-labelledby={`settings-group-${group.id}`}>
          <Typography id={`settings-group-${group.id}`} variant="h6">
            {t(group.labelKey)}
          </Typography>
          <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' } }}>
            {group.screens.map((def) => (
              <Card key={def.id} variant="outlined">
                <CardActionArea component={RouterLink} to={def.path}>
                  <CardContent>
                    <Typography variant="subtitle1">{t(def.labelKey)}</Typography>
                    <Typography variant="body2" color="text.secondary">
                      {t(`settingsHub.screen.${def.id}`)}
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Box>
        </Stack>
      ))}
    </SettingsPage>
  );
}
