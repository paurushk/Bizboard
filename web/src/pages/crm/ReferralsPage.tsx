import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { issueLeadFormToken } from '@/api/crm';
import { decideReferralReward, issueReferralCode, listReferralRewards, referralLeaderboard } from '@/api/growth';
import { useAuth } from '@/auth/AuthContext';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { isReferralsEnabled } from '@/config/features';
import { enumLabel } from '@/utils/enumLabels';
import { t } from '@/i18n';
import { CustomerField } from '@/pages/growth/widgets';
import { ModuleGate } from '@/pages/erp/erpShared';
import type { Customer } from '@/types/domain';
import { PageShell } from '@/pages/phase/phaseShared';

export function ReferralsPage() {
  if (!isReferralsEnabled()) {
    return <PageShell title={t('nav.referrals')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return (
    <ModuleGate module="crm" title={t('nav.referrals')}>
      <ReferralsInner />
    </ModuleGate>
  );
}

function ReferralsInner() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canDecide = user?.role === 'OWNER' || user?.role === 'MANAGER';
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [rewardType, setRewardType] = useState('FLAT');
  const [rewardValue, setRewardValue] = useState('0');
  const [issued, setIssued] = useState('');
  const [shareUrl, setShareUrl] = useState('');
  const [error, setError] = useState('');
  const board = useQuery({ queryKey: ['referral-board'], queryFn: referralLeaderboard });
  const rewards = useQuery({ queryKey: ['referral-rewards'], queryFn: listReferralRewards });
  const issue = useMutation({
    mutationFn: () => issueReferralCode({
      referrer_customer: customer!.id,
      reward_type: rewardType,
      reward_value: rewardValue || '0',
    }),
    onSuccess: async (row) => {
      setIssued(row.code);
      setError('');
      try {
        const token = await issueLeadFormToken();
        setShareUrl(`${window.location.origin}/lead-form/${token.token}?referral_code=${encodeURIComponent(row.code)}`);
      } catch (err) {
        setShareUrl('');
        setError(getErrorMessage(err));
      }
      void qc.invalidateQueries({ queryKey: ['referral-board'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: 'approve' | 'reject' | 'mark-paid' }) => decideReferralReward(id, decision),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['referral-rewards'] });
      void qc.invalidateQueries({ queryKey: ['referral-board'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.referrals')}</PageTitle>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField select size="small" label={t('growth.rewardType')} value={rewardType} onChange={(e) => setRewardType(e.target.value)} sx={{ minWidth: 140 }}>
          <MenuItem value="FLAT">{enumLabel('rewardType', 'FLAT')}</MenuItem>
          <MenuItem value="PERCENT">{enumLabel('rewardType', 'PERCENT')}</MenuItem>
        </TextField>
        <TextField size="small" label={t('growth.rewardValue')} value={rewardValue} onChange={(e) => setRewardValue(e.target.value)} />
        <Button variant="contained" disabled={!customer || issue.isPending} onClick={() => issue.mutate()}>{t('growth.issueCode')}</Button>
      </Stack>
      {issued ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography>{t('growth.code')}: {issued}</Typography>
          <Button
            size="small"
            href={`https://wa.me/?text=${encodeURIComponent(
              shareUrl ? `${shareUrl}` : `Use referral code ${issued}`,
            )}`}
            target="_blank"
            rel="noopener"
          >
            WhatsApp
          </Button>
        </Stack>
      ) : null}
      {error ? <Typography color="error">{error}</Typography> : null}
      {board.isLoading || rewards.isLoading ? <LoadingState /> : null}
      {board.isError ? <ErrorState message={getErrorMessage(board.error)} error={board.error} onRetry={() => void board.refetch()} /> : null}
      {rewards.isError ? <ErrorState message={getErrorMessage(rewards.error)} error={rewards.error} onRetry={() => void rewards.refetch()} /> : null}
      {!board.isLoading && !rewards.isLoading && !board.isError && !rewards.isError && (board.data ?? []).length === 0 && (rewards.data?.results ?? []).length === 0 ? (
        <EmptyState description={t('cog.emptyReferrals')} />
      ) : null}
      <Typography variant="subtitle2">{t('growth.leaderboard')}</Typography>
      {(board.data ?? []).map((row) => (
        <Typography key={row.code}>{row.code} · {row.referrerType} · {row.approvedTotal}</Typography>
      ))}
      <Typography variant="subtitle2">{t('growth.rewards')}</Typography>
      <Typography variant="caption" color="text.secondary">{t('growth.markPaidHint')}</Typography>
      {(rewards.data?.results ?? []).map((row) => (
        <Paper key={row.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2">
              #{row.opportunity} · {row.rewardAmount} · {row.rewardStatus}
              {row.rejectionReason === 'self_referral' ? ` — ${t('growth.selfReferralRejected')}` : ''}
            </Typography>
            {canDecide && row.rewardStatus === 'PENDING' ? (
              <>
                <Button size="small" onClick={() => decide.mutate({ id: row.id, decision: 'approve' })}>{t('growth.approve')}</Button>
                <Button size="small" onClick={() => decide.mutate({ id: row.id, decision: 'reject' })}>{t('growth.reject')}</Button>
              </>
            ) : null}
            {canDecide && row.rewardStatus === 'APPROVED' ? (
              <Button size="small" onClick={() => decide.mutate({ id: row.id, decision: 'mark-paid' })}>{t('growth.markPaid')}</Button>
            ) : null}
            <Typography variant="caption">{t('cog.settleNoJournal')}</Typography>
            <Button size="small" component={RouterLink} to="/sales/credit-notes/new">{t('cog.draftCreditNote')}</Button>
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}
