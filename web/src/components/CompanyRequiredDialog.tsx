import { useCallback, useEffect, useState } from 'react';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Typography from '@mui/material/Typography';
import { useAuth } from '@/auth/AuthContext';
import { useCompanySwitcher } from '@/hooks/useCompanySwitcher';
import { t } from '@/i18n';

type MembershipChoice = { id: number; name: string; role?: string };

function parseMemberships(detail: unknown): MembershipChoice[] {
  if (!detail || typeof detail !== 'object') return [];
  const raw = detail as { memberships?: unknown; Memberships?: unknown };
  const list = (raw.memberships ?? raw.Memberships) as unknown;
  if (!Array.isArray(list)) return [];
  return list
    .map((row): MembershipChoice | null => {
      const r = row as { id?: number; name?: string; role?: string; companyId?: number; companyName?: string };
      const id = Number(r.id ?? r.companyId);
      const name = String(r.name ?? r.companyName ?? '');
      return Number.isFinite(id) && id > 0 ? { id, name, role: r.role } : null;
    })
    .filter((m): m is MembershipChoice => m != null);
}

/** D-01: 409 COMPANY_REQUIRED opens a picker; switch then reload (no interceptor retry loop). */
export function CompanyRequiredDialog() {
  const { user } = useAuth();
  const { switchCompany, memberships } = useCompanySwitcher();
  const [open, setOpen] = useState(false);
  const [choices, setChoices] = useState<MembershipChoice[]>([]);

  useEffect(() => {
    const onRequired = (ev: Event) => {
      const parsed = parseMemberships((ev as CustomEvent).detail);
      setChoices(parsed.length ? parsed : memberships.map((m) => ({ id: m.companyId, name: m.companyName, role: m.role })));
      setOpen(true);
    };
    window.addEventListener('bizboard:company-required', onRequired);
    return () => window.removeEventListener('bizboard:company-required', onRequired);
  }, [memberships]);

  const pick = useCallback(
    async (companyId: number) => {
      await switchCompany(companyId);
      window.location.reload();
    },
    [switchCompany],
  );

  if (!user) return null;
  const rows = choices.length ? choices : memberships.map((m) => ({ id: m.companyId, name: m.companyName, role: m.role }));

  return (
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="xs">
      <DialogTitle>{t('locale.companyRequired')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t('locale.companyRequiredHelp')}
        </Typography>
        <List>
          {rows.map((m) => (
            <ListItemButton key={m.id} onClick={() => void pick(m.id)}>
              <ListItemText primary={m.name} secondary={m.role} />
            </ListItemButton>
          ))}
        </List>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
      </DialogActions>
    </Dialog>
  );
}
