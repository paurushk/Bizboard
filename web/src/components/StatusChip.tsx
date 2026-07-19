import Chip from '@mui/material/Chip';
import { t } from '@/i18n';
import type { ChipTone } from '@/utils/status';

const colorMap: Record<ChipTone, 'default' | 'success' | 'warning' | 'error' | 'info'> = {
  default: 'default',
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'info',
};

interface StatusChipProps {
  labelKey?: string;
  label?: string;
  tone: ChipTone;
  size?: 'small' | 'medium';
}

export function StatusChip({ labelKey, label, tone, size = 'small' }: StatusChipProps) {
  return (
    <Chip
      size={size}
      color={colorMap[tone]}
      label={label ?? (labelKey ? t(labelKey) : '')}
      variant={tone === 'default' ? 'outlined' : 'filled'}
    />
  );
}
