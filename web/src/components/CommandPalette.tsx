import { useEffect, useMemo, useState } from 'react';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import TextField from '@mui/material/TextField';
import { useNavigate } from 'react-router-dom';
import { t, useLocale } from '@/i18n';
import { filterNav, type NavItem } from '@/navigation/menu';
import { useAuth } from '@/auth/AuthContext';

function flatten(items: NavItem[], user: ReturnType<typeof useAuth>['user']): Array<{ path: string; label: string }> {
  const out: Array<{ path: string; label: string }> = [];
  for (const item of items) {
    if (item.visible && !item.visible(user)) continue;
    if (item.path) out.push({ path: item.path, label: t(item.labelKey) });
    if (item.children) out.push(...flatten(item.children, user));
  }
  return out;
}

/** Ctrl/Cmd+K lists existing navigation routes. */
export function CommandPalette() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const locale = useLocale();
  // The same list the menu shows (feature flags, packs, not-ready modules), in the current language.
  // eslint-disable-next-line react-hooks/exhaustive-deps -- locale changes the labels t() returns
  const routes = useMemo(() => flatten(filterNav(user), user), [user, locale]);
  const shown = routes.filter((row) => row.label.toLowerCase().includes(q.trim().toLowerCase()) || row.path.includes(q.trim().toLowerCase())).slice(0, 20);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
      <DialogTitle>{t('cog.commandPalette')}</DialogTitle>
      <TextField
        autoFocus
        size="small"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        sx={{ mx: 2, mb: 1 }}
      />
      <List dense>
        {shown.map((row) => (
          <ListItemButton
            key={row.path}
            onClick={() => {
              setOpen(false);
              setQ('');
              navigate(row.path);
            }}
          >
            <ListItemText primary={row.label} secondary={row.path} />
          </ListItemButton>
        ))}
      </List>
    </Dialog>
  );
}
