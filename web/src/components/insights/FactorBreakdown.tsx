import Box from '@mui/material/Box';
import LinearProgress from '@mui/material/LinearProgress';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';
import { useMaskedText } from './MoneyText';
import type { HealthFactor } from '@/types/domain';

export type { HealthFactor };

export function FactorBreakdown({ factors }: { factors: HealthFactor[] }) {
  const mask = useMaskedText();
  return (
    <Stack spacing={1.5}>
      {factors.map((f) => {
        const available = f.available !== false && f.score != null;
        const score = available ? Number(f.score) : 0;
        return (
          <Box key={f.key}>
            <Stack direction="row" justifyContent="space-between" alignItems="baseline">
              <Typography variant="body2" fontWeight={600}>
                {f.label}
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  {t('insights.factorWeight', { pct: (Number(f.weight) * 100).toFixed(0) })}
                </Typography>
              </Typography>
              <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                {available ? Math.round(score) : t('insights.factorUnavailable')}
              </Typography>
            </Stack>
            {available ? (
              <LinearProgress
                aria-label={f.label}
                variant="determinate"
                value={Math.max(0, Math.min(100, score))}
                sx={{ height: 8, borderRadius: 1, mt: 0.5 }}
                color={score >= 70 ? 'success' : score >= 45 ? 'warning' : 'error'}
              />
            ) : null}
            {f.detail ? (
              <Typography variant="caption" color="text.secondary">
                {mask(f.detail)}
              </Typography>
            ) : null}
          </Box>
        );
      })}
    </Stack>
  );
}
