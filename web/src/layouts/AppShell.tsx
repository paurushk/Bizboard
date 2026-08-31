import { useEffect, useMemo, useState } from 'react';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import Alert from '@mui/material/Alert';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import Collapse from '@mui/material/Collapse';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Toolbar from '@mui/material/Toolbar';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { Outlet, NavLink, Link as RouterLink, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { UniversalSearch } from '@/components/UniversalSearch';
import { CompanySwitcher } from '@/components/CompanySwitcher';
import { CompanyRequiredDialog } from '@/components/CompanyRequiredDialog';
import { LocaleSwitcher } from '@/components/LocaleSwitcher';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { getLocale, subscribeLocale, t } from '@/i18n';
import { filterNav, type NavItem } from '@/navigation/menu';
import { listDrafts } from '@/offline/invoiceDraftCache';

const DRAWER_WIDTH = 272;
const MOBILE_BILLING_TIP_KEY = 'bizboard.dismiss.mobileBillingTip';

/** Re-render shell copy when locale changes without a full reload (FE-18). */
function useLocaleTick() {
  const [, setTick] = useState(0);
  useEffect(() => subscribeLocale(() => setTick((n) => n + 1)), []);
  return getLocale();
}

function NavSection({
  item,
  onNavigate,
}: {
  item: NavItem;
  onNavigate?: () => void;
}) {
  const location = useLocation();
  const childActive = item.children?.some((c) => c.path && location.pathname.startsWith(c.path));
  const [open, setOpen] = useState(Boolean(childActive));

  useEffect(() => {
    if (childActive) setOpen(true);
  }, [childActive]);

  if (!item.children) {
    return (
      <ListItemButton
        component={NavLink}
        to={item.path ?? '/'}
        selected={location.pathname === item.path}
        onClick={onNavigate}
      >
        <ListItemText primary={t(item.labelKey)} />
      </ListItemButton>
    );
  }

  return (
    <>
      <ListItemButton
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`nav-section-${item.id}`}
      >
        <ListItemText primary={t(item.labelKey)} />
        {open ? <ExpandLess aria-hidden /> : <ExpandMore aria-hidden />}
      </ListItemButton>
      <Collapse in={open} timeout="auto" unmountOnExit id={`nav-section-${item.id}`}>
        <List component="div" disablePadding>
          {item.children.map((child) => (
            <ListItemButton
              key={child.id}
              component={NavLink}
              to={child.path ?? '/'}
              selected={location.pathname === child.path}
              sx={{ pl: 4 }}
              onClick={onNavigate}
            >
              <ListItemText primary={t(child.labelKey)} />
            </ListItemButton>
          ))}
        </List>
      </Collapse>
    </>
  );
}

export function AppShell() {
  useLocaleTick();
  const flagEpoch = useFeatureFlagEpoch();
  const { user, logout, usingMockSession } = useAuth();
  const { writesBlocked } = useSubscriptionGate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hideBillingTip, setHideBillingTip] = useState(
    () => typeof window !== 'undefined' && localStorage.getItem(MOBILE_BILLING_TIP_KEY) === '1',
  );
  const [pendingDrafts, setPendingDrafts] = useState(0);
  const items = useMemo(() => filterNav(user), [user, flagEpoch]);

  useEffect(() => {
    const companyId = user?.companyId;
    const userId = user?.id;
    if (!companyId || !userId) {
      setPendingDrafts(0);
      return;
    }
    const refresh = () => {
      void listDrafts(companyId, userId)
        .then((drafts) => setPendingDrafts(drafts.filter((d) => d.idempotencyKey !== 'purchase-editor-draft').length))
        .catch(() => undefined);
    };
    refresh();
    window.addEventListener('online', refresh);
    const id = window.setInterval(refresh, 30000);
    return () => {
      window.removeEventListener('online', refresh);
      window.clearInterval(id);
    };
  }, [user?.companyId, user?.id]);

  // BB-000242: close mobile drawer after navigation.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const closeMobile = () => setMobileOpen(false);
  const showBillingTip =
    !hideBillingTip &&
    (location.pathname === '/pos' ||
      /\/(sales|purchases)\/(new|history\/\d+\/edit)/.test(location.pathname) ||
      /\/(sales|purchases)\/(credit-notes|debit-notes|orders|delivery-challans)\/(new|\d+)/.test(
        location.pathname,
      ));

  const drawer = (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Toolbar sx={{ px: 2 }}>
        <Typography variant="h6" color="primary.main">
          {t('app.name')}
        </Typography>
      </Toolbar>
      <Divider />
      <List sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
        {items.map((item) => (
          <NavSection key={item.id} item={item} onNavigate={closeMobile} />
        ))}
      </List>
      <Divider />
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" fontWeight={600}>
          {user?.fullName || user?.email}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {user?.role?.replace(/_/g, ' ')}
        </Typography>
        <Button fullWidth variant="outlined" size="small" onClick={() => void logout()}>
          {t('auth.logout')}
        </Button>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <Box
        component="a"
        href="#main-content"
        sx={{
          position: 'absolute',
          left: -10000,
          top: 8,
          zIndex: (theme) => theme.zIndex.tooltip + 1,
          bgcolor: 'background.paper',
          color: 'text.primary',
          px: 2,
          py: 1,
          borderRadius: 1,
          boxShadow: 2,
          textDecoration: 'none',
          '&:focus': { left: 8 },
        }}
      >
        {t('a11y.skipToContent')}
      </Box>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
          // UXW2-015: keep header chrome from intercepting clicks on form fields below.
          overflow: { xs: 'visible', sm: 'hidden' },
        }}
      >
        <Toolbar sx={{ gap: 1, minHeight: 64, flexWrap: { xs: 'wrap', sm: 'nowrap' } }}>
          <IconButton
            color="inherit"
            edge="start"
            sx={{ display: { md: 'none' } }}
            onClick={() => setMobileOpen(true)}
            aria-label={t('a11y.openNavigation')}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ flexGrow: { xs: 1, sm: 0 }, mr: { sm: 2 }, flexShrink: 0 }}>
            {t('app.name')}
          </Typography>
          <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: { xs: 'stretch', sm: 'center' }, minWidth: 0 }}>
            <UniversalSearch />
          </Box>
          {pendingDrafts > 0 &&
          (/^\/(pos|sales|purchases|offline-outbox)/.test(location.pathname) ||
            location.pathname.startsWith('/inventory/stock-counts') ||
            location.pathname.startsWith('/inventory/transfers')) ? (
            <Chip
              component={RouterLink}
              to="/offline-outbox"
              clickable
              size="small"
              color="warning"
              label={t('billing.outboxPendingBadge', { count: pendingDrafts })}
            />
          ) : null}
          <CompanySwitcher />
          <LocaleSwitcher />
          <Typography variant="body2" sx={{ display: { xs: 'none', lg: 'block' } }}>
            {user?.email}
          </Typography>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }} aria-label={t('a11y.mainNav')}>
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          open
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
          }}
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        id="main-content"
        tabIndex={-1}
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          p: { xs: 2, md: 3 },
          background:
            'linear-gradient(180deg, #E8F3F1 0%, #F3F6F5 140px, #F3F6F5 100%)',
          outline: 'none',
        }}
      >
        <Toolbar />
        <Box sx={{ minHeight: 8 }} aria-hidden />
        {usingMockSession ? (
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('common.mockBanner')}
          </Alert>
        ) : null}
        {writesBlocked ? (
          <Alert
            severity="error"
            sx={{ mb: 2 }}
            action={
              <Button component={RouterLink} to="/settings/billing" color="inherit" size="small">
                {t('nav.billing')}
              </Button>
            }
          >
            {t('billing.writesBlocked')}
          </Alert>
        ) : null}
        {showBillingTip ? (
          <Alert
            severity="info"
            sx={{ mb: 2, display: { xs: 'flex', md: 'none' } }}
            onClose={() => {
              localStorage.setItem(MOBILE_BILLING_TIP_KEY, '1');
              setHideBillingTip(true);
            }}
          >
            {t('billing.mobileBillingTip')}
          </Alert>
        ) : null}
        <Outlet />
        <CompanyRequiredDialog />
      </Box>
    </Box>
  );
}
