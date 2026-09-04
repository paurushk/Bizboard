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
import Alert from '@mui/material/Alert';
import { getErrorMessage } from '@/api/client';
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
  const { user, logout } = useAuth();
  const { switchCompany, memberships } = useCompanySwitcher();
  const [open, setOpen] = useState(false);
  const [choices, setChoices] = useState<MembershipChoice[]>([]);
  const [error, setError] = useState('');
  const [switching, setSwitching] = useState(false);

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
      // F3-043: surface a failed switch instead of swallowing the rejection,
      // and keep the dialog open so the user can retry.
      setError('');
      setSwitching(true);
      try {
        await switchCompany(companyId);
        window.location.reload();
      } catch (err) {
        setError(getErrorMessage(err));
        setSwitching(false);
      }
    },
    [switchCompany],
  );

  if (!user) return null;
  const rows = choices.length ? choices : memberships.map((m) => ({ id: m.companyId, name: m.companyName, role: m.role }));

  return (
    // F3-043: this dialog gates a page that has no company context — it must not
    // be dismissable into a dead screen. No backdrop/escape close; the only way
    // out other than picking a company is to sign out.
    <Dialog open={open} fullWidth maxWidth="xs">
      <DialogTitle>{t('locale.companyRequired')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          {t('locale.companyRequiredHelp')}
        </Typography>
        {error ? (
          <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError('')}>
            {error}
          </Alert>
        ) : null}
        <List>
          {rows.map((m) => (
            <ListItemButton key={m.id} disabled={switching} onClick={() => void pick(m.id)}>
              <ListItemText primary={m.name} secondary={m.role} />
            </ListItemButton>
          ))}
        </List>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => void logout()}>{t('auth.logout')}</Button>
      </DialogActions>
    </Dialog>
  );
}
