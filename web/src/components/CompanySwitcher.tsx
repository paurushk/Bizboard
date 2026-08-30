import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import MenuItem from '@mui/material/MenuItem';
import Select, { type SelectChangeEvent } from '@mui/material/Select';
import Snackbar from '@mui/material/Snackbar';
import Alert from '@mui/material/Alert';
import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/AuthContext';
import { useCompanySwitcher } from '@/hooks/useCompanySwitcher';
import { getErrorMessage } from '@/api/client';
import { t } from '@/i18n';
import { HelpWhyLink } from '@/pages/help/HelpWhyLink';

export function CompanySwitcher() {
  const { user } = useAuth();
  const { memberships, hasMultiple, loading, switchCompany, error } = useCompanySwitcher();
  const [dismissed, setDismissed] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

  useEffect(() => {
    setDismissed(false);
  }, [error, switchError]);

  const activeId = memberships.find((m) => m.isActiveSelection)?.companyId ?? user?.companyId;
  const banner = switchError || error;

  const onChange = (event: SelectChangeEvent<number>) => {
    const nextId = Number(event.target.value);
    if (nextId && nextId !== activeId) {
      setSwitchError(null);
      void switchCompany(nextId)
        .then(() => window.location.reload())
        .catch((err) => setSwitchError(getErrorMessage(err)));
    }
  };

  return (
    <>
      <Snackbar open={Boolean(banner) && !dismissed} autoHideDuration={8000} onClose={() => setDismissed(true)}>
        <Alert severity="error" variant="filled" onClose={() => setDismissed(true)}>
          {banner ?? t('common.membershipsLoadFailed')}
          <HelpWhyLink message={banner ?? t('common.membershipsLoadFailed')} />
        </Alert>
      </Snackbar>
      {hasMultiple && user ? (
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
      ) : null}
    </>
  );
}
