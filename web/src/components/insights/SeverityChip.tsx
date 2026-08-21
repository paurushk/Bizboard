import Chip from '@mui/material/Chip';

export type AlertSeverity = 'critical' | 'warning' | 'info' | string;

export function severityColor(
  severity: AlertSeverity,
): 'error' | 'warning' | 'info' | 'default' {
  const s = (severity || '').toLowerCase();
  if (s === 'critical') return 'error';
  if (s === 'warning') return 'warning';
  if (s === 'info') return 'info';
  return 'default';
}

export function SeverityChip({
  severity,
  label,
  size = 'small',
}: {
  severity: AlertSeverity;
  label?: string;
  size?: 'small' | 'medium';
}) {
  return (
    <Chip
      size={size}
      color={severityColor(severity)}
      label={label ?? severity}
      sx={{ textTransform: 'capitalize' }}
    />
  );
}
