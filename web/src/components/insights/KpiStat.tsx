import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import { MoneyText } from './MoneyText';

export function KpiStat({
  label,
  value,
  money = false,
  deltaLabel,
  limitedData = false,
  dense = false,
}: {
  label: string;
  value: string | number | null | undefined;
  money?: boolean;
  deltaLabel?: string | null;
  limitedData?: boolean;
  dense?: boolean;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{ p: dense ? 1.5 : 2.5, height: '100%', position: 'relative' }}
    >
      {limitedData ? (
        <Typography
          variant="caption"
          color="warning.main"
          sx={{ position: 'absolute', top: 6, right: 8 }}
        >
          Limited data
        </Typography>
      ) : null}
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Box sx={{ mt: 1 }}>
        {money ? (
          <Typography variant={dense ? 'h6' : 'h5'} component="div">
            <MoneyText value={value} />
          </Typography>
        ) : (
          <Typography variant={dense ? 'h6' : 'h5'}>{value ?? '—'}</Typography>
        )}
      </Box>
      {deltaLabel ? (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          {deltaLabel}
        </Typography>
      ) : null}
    </Paper>
  );
}
