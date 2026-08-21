import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select, { type SelectChangeEvent } from '@mui/material/Select';
import { useAuth } from '@/auth/AuthContext';
import { useCompanySwitcher } from '@/hooks/useCompanySwitcher';
import { t } from '@/i18n';

export function CompanySwitcher() {
  const { user } = useAuth();
  const { memberships, hasMultiple, loading, switchCompany } = useCompanySwitcher();

  if (!hasMultiple || !user) return null;

  const activeId = memberships.find((m) => m.isActiveSelection)?.companyId ?? user.companyId;

  const onChange = (event: SelectChangeEvent<number>) => {
    const nextId = Number(event.target.value);
    if (nextId && nextId !== activeId) {
      void switchCompany(nextId).then(() => window.location.reload());
    }
  };

  return (
    <FormControl size="small" sx={{ minWidth: 160 }} disabled={loading}>
      <InputLabel id="company-switcher-label">{t('locale.companySwitcher')}</InputLabel>
      <Select
        labelId="company-switcher-label"
        label={t('locale.companySwitcher')}
        value={activeId}
        onChange={onChange}
      >
        {memberships.map((m) => (
          <MenuItem key={m.companyId} value={m.companyId}>
            {m.companyName}
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}
