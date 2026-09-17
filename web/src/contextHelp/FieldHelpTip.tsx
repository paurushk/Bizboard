import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import { t } from '@/i18n';

/**
 * Field/action-level ⓘ tooltip. Does not open the page Help drawer
 * and never triggers a business action.
 */
export function FieldHelpTip({ title, slot }: { title: string; slot?: string }) {
  return (
    <Tooltip title={title}>
      <IconButton
        type="button"
        size="small"
        aria-label={t('help.fieldTipAria')}
        tabIndex={0}
        data-testid="field-help-tip"
        data-help-slot={slot}
      >
        <InfoOutlinedIcon fontSize="inherit" color="action" />
      </IconButton>
    </Tooltip>
  );
}
