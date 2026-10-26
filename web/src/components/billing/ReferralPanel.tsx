import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { getReferralPanel } from '@/api/billing';
import { isRuntimeFlagEnabled, useFeatureFlagEpoch } from '@/config/featureFlags';
import { t } from '@/i18n';

/**
 * D-19 (BB-139): the owner's "Refer a business" link. Shown only while the company's
 * ENABLE_SAAS_REFERRALS flag is on. The reward is settled by Bizboard staff by hand, so the panel
 * promises contact, not an amount. Counts only: never which businesses signed up.
 */
export function ReferralPanel({ companyKey }: { companyKey: unknown }) {
  useFeatureFlagEpoch();
  const on = isRuntimeFlagEnabled('ENABLE_SAAS_REFERRALS');
  const panel = useQuery({ queryKey: ['saas-referral', companyKey], queryFn: getReferralPanel, enabled: on, retry: false });
  const [copied, setCopied] = useState(false);
  if (!on || !panel.data) return null;
  const link = `${window.location.origin}/register?ref=${encodeURIComponent(panel.data.code)}`;
  const share = `https://wa.me/?text=${encodeURIComponent(t('saasBilling.referralShareText', { link }))}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">{t('saasBilling.referralTitle')}</Typography>
        <Typography variant="body2" color="text.secondary">{t('saasBilling.referralHelp')}</Typography>
        {panel.data.isActive ? (
          <>
            <TextField
              size="small"
              label={t('saasBilling.referralLink')}
              value={link}
              InputProps={{ readOnly: true }}
              onFocus={(e) => e.target.select()}
              fullWidth
            />
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Button variant="outlined" onClick={() => void copy()}>
                {copied ? t('saasBilling.referralCopied') : t('saasBilling.referralCopy')}
              </Button>
              <Button variant="outlined" component="a" href={share} target="_blank" rel="noopener noreferrer">
                {t('saasBilling.referralShare')}
              </Button>
            </Stack>
          </>
        ) : (
          <Alert severity="info">{t('saasBilling.referralOff')}</Alert>
        )}
        <Typography variant="body2">
          {t('saasBilling.referralCounts', { signedUp: panel.data.signedUp, qualified: panel.data.qualified })}
        </Typography>
        <Typography variant="caption" color="text.secondary">{t('saasBilling.referralPrivacy')}</Typography>
      </Stack>
    </Paper>
  );
}
