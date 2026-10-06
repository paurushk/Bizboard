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
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Snackbar from '@mui/material/Snackbar';
import Toolbar from '@mui/material/Toolbar';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { useQuery } from '@tanstack/react-query';
import { Outlet, NavLink, Link as RouterLink, useLocation } from 'react-router-dom';
import { getCompany } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { usePrivacyMask } from '@/privacy/PrivacyMask';
import { CommandPalette } from '@/components/CommandPalette';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { UniversalSearch } from '@/components/UniversalSearch';
import { CompanySwitcher } from '@/components/CompanySwitcher';
import { CompanyRequiredDialog } from '@/components/CompanyRequiredDialog';
import { LocaleSwitcher } from '@/components/LocaleSwitcher';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { useFeatureFlagEpoch } from '@/config/featureFlags';
import { getLocale, subscribeLocale, t } from '@/i18n';
import { filterNav, isNavPathActive, type NavItem } from '@/navigation/menu';
import { listDrafts } from '@/offline/invoiceDraftCache';
import { drainPodPhotos } from '@/offline/photoOutbox';

const DRAWER_WIDTH = 272;
const MOBILE_BILLING_TIP_KEY = 'bizboard.dismiss.mobileBillingTip';

function navPathSelected(pathname: string, path?: string): boolean {
  return isNavPathActive(pathname, path);
}

/** Re-render shell copy when locale changes without a full reload (FE-18). */
function useLocaleTick() {
  const [, setTick] = useState(0);
  useEffect(() => subscribeLocale(() => setTick((n) => n + 1)), []);
  return getLocale();
}

function navBranchActive(item: NavItem, pathname: string): boolean {
  if (navPathSelected(pathname, item.path)) return true;
  return Boolean(item.children?.some((child) => navBranchActive(child, pathname)));
}

function NavSection({
  item,
  onNavigate,
  nested = false,
}: {
  item: NavItem;
  onNavigate?: () => void;
  nested?: boolean;
}) {
  const location = useLocation();
  const childActive = item.children?.some((child) => navBranchActive(child, location.pathname));
  const [open, setOpen] = useState(Boolean(childActive));

  // Expand the section when navigation moves into it.
  const [seenChildActive, setSeenChildActive] = useState(Boolean(childActive));
  if (seenChildActive !== Boolean(childActive)) {
    setSeenChildActive(Boolean(childActive));
    if (childActive) setOpen(true);
  }

  if (!item.children) {
    return (
      <ListItemButton
        component={NavLink}
        to={item.path ?? '/'}
        selected={navPathSelected(location.pathname, item.path)}
        onClick={onNavigate}
        sx={nested ? { pl: 4 } : undefined}
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
        sx={nested ? { pl: 4 } : undefined}
      >
        <ListItemText primary={t(item.labelKey)} />
        {open ? <ExpandLess aria-hidden /> : <ExpandMore aria-hidden />}
      </ListItemButton>
      <Collapse in={open} timeout="auto" unmountOnExit id={`nav-section-${item.id}`}>
        <List component="div" disablePadding>
          {item.children.map((child) =>
            child.children?.length ? (
              <NavSection key={child.id} item={child} onNavigate={onNavigate} nested />
            ) : (
              <ListItemButton
                key={child.id}
                component={NavLink}
                to={child.path ?? '/'}
                selected={navPathSelected(location.pathname, child.path)}
                sx={{ pl: nested ? 6 : 4 }}
                onClick={onNavigate}
              >
                <ListItemText primary={t(child.labelKey)} />
              </ListItemButton>
            ),
          )}
        </List>
      </Collapse>
    </>
  );
}

export function AppShell() {
  useLocaleTick();
  const flagEpoch = useFeatureFlagEpoch();
  const { user, logout, usingMockSession } = useAuth();
  const { privacyMask, togglePrivacyMask } = usePrivacyMask();
  const { writesBlocked } = useSubscriptionGate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hideBillingTip, setHideBillingTip] = useState(
    () => typeof window !== 'undefined' && localStorage.getItem(MOBILE_BILLING_TIP_KEY) === '1',
  );
  const [queuedDrafts, setPendingDrafts] = useState(0);
  // Nothing is pending for a signed-out user, whatever the last count was.
  const pendingDrafts = user?.companyId && user?.id ? queuedDrafts : 0;
  const [pwaReloadFn, setPwaReloadFn] = useState<(() => void) | null>(null);
  const items = useMemo(() => filterNav(user), [user, flagEpoch]);
  const company = useQuery({
    queryKey: ['company'],
    queryFn: getCompany,
    enabled: Boolean(user?.companyId),
  });
  const companyName = company.data?.name?.trim() ?? '';

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.shiftKey || e.ctrlKey || e.metaKey || e.altKey || e.key.toLowerCase() !== 'p') return;
      const tag = (document.activeElement as HTMLElement | null)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      e.preventDefault();
      togglePrivacyMask();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [togglePrivacyMask]);

  useEffect(() => {
    const handler = (e: Event) => {
      const custom = e as CustomEvent<{ reload?: () => void }>;
      if (custom.detail?.reload) {
        setPwaReloadFn(() => custom.detail.reload);
      }
    };
    window.addEventListener('bizboard:pwa-update-available', handler);
    return () => window.removeEventListener('bizboard:pwa-update-available', handler);
  }, []);

  useEffect(() => {
    const companyId = user?.companyId;
    const userId = user?.id;
    if (!companyId || !userId) return;
    const refresh = () => {
      void listDrafts(companyId, userId)
        .then((drafts) => setPendingDrafts(drafts.filter((d) => d.idempotencyKey !== 'purchase-editor-draft').length))
        .catch(() => undefined);
      void drainPodPhotos().catch(() => undefined);
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
  const [seenPathname, setSeenPathname] = useState(location.pathname);
  if (seenPathname !== location.pathname) {
    setSeenPathname(location.pathname);
    setMobileOpen(false);
  }

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
        <Typography variant="h6" color="primary.main" noWrap>
          {t('app.name')}
        </Typography>
        {companyName ? (
          <Tooltip title={companyName}>
            <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: { xs: 120, sm: 180 }, ml: 1 }}>
              {companyName}
            </Typography>
          </Tooltip>
        ) : null}
      </Toolbar>
      <Divider />
      <List sx={{ flex: 1, overflowY: 'auto', py: 1 }}>
        {items.map((item) => (
          // WCAG 1.3.1: a <ul> may only directly contain <li>. NavSection emits
          // a ListItemButton (or a header + Collapse); wrap each in an <li>.
          <ListItem key={item.id} disablePadding sx={{ display: 'block' }}>
            <NavSection item={item} onNavigate={closeMobile} />
          </ListItem>
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
        <Toolbar sx={{ gap: 1, minHeight: { xs: 56, sm: 64 } }}>
          <IconButton
            color="inherit"
            edge="start"
            sx={{ display: { md: 'none' } }}
            onClick={() => setMobileOpen(true)}
            aria-label={t('a11y.openNavigation')}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ flexShrink: 0 }}>
            {t('app.name')}
          </Typography>
          {companyName ? (
            <Tooltip title={companyName}>
              <Typography variant="body2" noWrap sx={{ maxWidth: { xs: 96, sm: 200 }, opacity: 0.9 }}>
                {companyName}
              </Typography>
            </Tooltip>
          ) : null}
          <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: 'center', minWidth: 0 }}>
            <Box sx={{ display: { xs: 'none', sm: 'block' }, width: '100%' }}>
              <UniversalSearch />
            </Box>
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
          <Button color="inherit" size="small" onClick={togglePrivacyMask}>
            {privacyMask ? t('app.showAmounts') : t('app.hideAmounts')}
          </Button>
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
        className={privacyMask ? 'privacy-mask' : undefined}
        sx={{
          flexGrow: 1,
          width: { xs: '100%', md: `calc(100% - ${DRAWER_WIDTH}px)` },
          maxWidth: '100%',
          overflowX: 'hidden',
          '&.privacy-mask .MuiPaper-root, &.privacy-mask .MuiTableCell-root': { filter: 'blur(6px)' },
          boxSizing: 'border-box',
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
        {/* F3-044: a per-route boundary keyed by pathname — a render-time
            crash on one page now shows an inline fallback in place of just
            that page's content; nav, company switcher, and the rest of the
            shell (all siblings, outside this boundary) stay usable, and
            navigating to a different route remounts the boundary fresh
            instead of being stuck on the old crash until a full reload. */}
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
        <CommandPalette />
        <CompanyRequiredDialog />
        <Snackbar
          open={Boolean(pwaReloadFn)}
          message="A new version of Bizboard is available."
          action={
            <Button
              color="primary"
              size="small"
              variant="contained"
              onClick={() => {
                if (pwaReloadFn) pwaReloadFn();
              }}
            >
              {t('sweep2.updateNow')}
            </Button>
          }
        />
      </Box>
    </Box>
  );
}
