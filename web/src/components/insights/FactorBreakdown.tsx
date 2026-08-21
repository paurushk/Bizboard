import Box from '@mui/material/Box';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

export type HealthFactor = {
  key: string;
  label: string;
  score: number;
  weight: number;
  detail?: string;
};

export function FactorBreakdown({ factors }: { factors: HealthFactor[] }) {
  return (
    <Stack spacing={1.5}>
      {factors.map((f) => (
        <Box key={f.key}>
          <Stack direction="row" justifyContent="space-between" alignItems="baseline">
            <Typography variant="body2" fontWeight={600}>
              {f.label}
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                weight {(f.weight * 100).toFixed(0)}%
              </Typography>
            </Typography>
            <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
              {Math.round(f.score)}
            </Typography>
          </Stack>
          <LinearProgress
            variant="determinate"
            value={Math.max(0, Math.min(100, f.score))}
            sx={{ height: 8, borderRadius: 1, mt: 0.5 }}
            color={f.score >= 70 ? 'success' : f.score >= 45 ? 'warning' : 'error'}
          />
          {f.detail ? (
            <Typography variant="caption" color="text.secondary">
              {f.detail}
            </Typography>
          ) : null}
        </Box>
      ))}
    </Stack>
  );
}
