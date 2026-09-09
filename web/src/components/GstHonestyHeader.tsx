import Alert from '@mui/material/Alert';
import { t } from '@/i18n';

/** Shared honesty banner on every GSTR page (R-080): offline aid, not GSTN filing. */
export function GstHonestyHeader() {
  return <Alert severity="info">{t('gstHonesty.offlineAid')}</Alert>;
}
