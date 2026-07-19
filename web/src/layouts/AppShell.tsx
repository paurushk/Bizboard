import { useMemo, useState } from 'react';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import Alert from '@mui/material/Alert';
import AppBar from '@mui/material/AppBar';
import Box from '@mui/material/Box';
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
import { Outlet, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { UniversalSearch } from '@/components/UniversalSearch';
import { t } from '@/i18n';
import { filterNav, type NavItem } from '@/navigation/menu';

const DRAWER_WIDTH = 272;

function NavSection({ item }: { item: NavItem }) {
  const location = useLocation();
  const childActive = item.children?.some((c) => c.path && location.pathname.startsWith(c.path));
  const [open, setOpen] = useState(Boolean(childActive));

  if (!item.children) {
    return (
      <ListItemButton
        component={NavLink}
        to={item.path ?? '/'}
        selected={location.pathname === item.path}
      >
        <ListItemText primary={t(item.labelKey)} />
      </ListItemButton>
    );
  }

  return (
    <>
      <ListItemButton onClick={() => setOpen((v) => !v)}>
        <ListItemText primary={t(item.labelKey)} />
        {open ? <ExpandLess /> : <ExpandMore />}
      </ListItemButton>
      <Collapse in={open} timeout="auto" unmountOnExit>
        <List component="div" disablePadding>
          {item.children.map((child) => (
            <ListItemButton
              key={child.id}
              component={NavLink}
              to={child.path ?? '/'}
              selected={location.pathname === child.path}
              sx={{ pl: 4 }}
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
  const { user, logout, usingMockSession } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const items = useMemo(() => filterNav(user), [user]);

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
          <NavSection key={item.id} item={item} />
        ))}
      </List>
      <Divider />
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" fontWeight={600}>
          {user?.fullName || user?.email}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {user?.role.replace(/_/g, ' ')}
        </Typography>
        <Button fullWidth variant="outlined" size="small" onClick={() => void logout()}>
          {t('auth.logout')}
        </Button>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { md: `${DRAWER_WIDTH}px` },
        }}
      >
        <Toolbar sx={{ gap: 2, flexWrap: 'wrap' }}>
          <IconButton
            color="inherit"
            edge="start"
            sx={{ display: { md: 'none' } }}
            onClick={() => setMobileOpen(true)}
          >
            <MenuIcon />
          </IconButton>
          <Typography variant="h6" sx={{ flexGrow: { xs: 1, sm: 0 }, mr: { sm: 2 } }}>
            {t('app.name')}
          </Typography>
          <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: { xs: 'stretch', sm: 'center' } }}>
            <UniversalSearch />
          </Box>
          <Typography variant="body2" sx={{ display: { xs: 'none', lg: 'block' } }}>
            {user?.email}
          </Typography>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: DRAWER_WIDTH }, flexShrink: { md: 0 } }}>
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
        sx={{
          flexGrow: 1,
          width: { md: `calc(100% - ${DRAWER_WIDTH}px)` },
          p: { xs: 2, md: 3 },
          background:
            'linear-gradient(180deg, #E8F3F1 0%, #F3F6F5 140px, #F3F6F5 100%)',
        }}
      >
        <Toolbar />
        {usingMockSession ? (
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('common.mockBanner')}
          </Alert>
        ) : null}
        <Outlet />
      </Box>
    </Box>
  );
}
