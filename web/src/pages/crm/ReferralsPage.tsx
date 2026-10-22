import { useState } from 'react';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import { issueLeadFormToken } from '@/api/crm';
import {
  decideReferralReward,
  deactivateReferralCode,
  issueReferralCode,
  listReferralCodes,
  listReferralRewards,
  referralLeaderboard,
  type ReferralCodeRow,
  type ReferralReward,
} from '@/api/growth';
import { useAuth } from '@/auth/AuthContext';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { isReferralsEnabled } from '@/config/features';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
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

function rewardValueProblem(type: string, raw: string): boolean {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) return true;
  return type === 'PERCENT' && value > 100;
}

function ReferralsInner() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { writesBlocked } = useSubscriptionGate();
  const isManager = user?.role === 'OWNER' || user?.role === 'MANAGER';
  const canDecide = isManager && !writesBlocked;
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [rewardType, setRewardType] = useState('FLAT');
  const [rewardValue, setRewardValue] = useState('0');
  const [issued, setIssued] = useState('');
  const [shareUrl, setShareUrl] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [payTarget, setPayTarget] = useState<ReferralReward | null>(null);
  const [reverseTarget, setReverseTarget] = useState<ReferralReward | null>(null);
  const [codeTarget, setCodeTarget] = useState<ReferralCodeRow | null>(null);
  const board = useQuery({ queryKey: ['referral-board'], queryFn: referralLeaderboard });
  const rewards = useQuery({ queryKey: ['referral-rewards'], queryFn: listReferralRewards });
  const codes = useQuery({ queryKey: ['referral-codes'], queryFn: listReferralCodes });

  const linkFor = async (code: string) => {
    const token = await issueLeadFormToken();
    return `${window.location.origin}/lead-form/${token.token}?referral_code=${encodeURIComponent(code)}`;
  };

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
        setShareUrl(await linkFor(row.code));
      } catch (err) {
        setShareUrl('');
        setError(getErrorMessage(err));
      }
      void qc.invalidateQueries({ queryKey: ['referral-board'] });
      void qc.invalidateQueries({ queryKey: ['referral-codes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: 'approve' | 'reject' | 'mark-paid' | 'reverse' }) => decideReferralReward(id, decision),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['referral-rewards'] });
      void qc.invalidateQueries({ queryKey: ['referral-board'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
    onSettled: () => {
      setPayTarget(null);
      setReverseTarget(null);
    },
  });
  const deactivate = useMutation({
    mutationFn: (id: number) => deactivateReferralCode(id),
    onSuccess: () => {
      setError('');
      void qc.invalidateQueries({ queryKey: ['referral-codes'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
    onSettled: () => setCodeTarget(null),
  });

  // Clipboard needs HTTPS and permission; when it fails the link is shown so it can still be copied by hand.
  const copyLink = async (code: string) => {
    try {
      const url = await linkFor(code);
      try {
        await navigator.clipboard.writeText(url);
        setNotice(t('osPlan.formLinkCopied'));
      } catch {
        setNotice(t('growth.copyFailed', { url }));
      }
    } catch (err) {
      setError(getErrorMessage(err));
    }
  };

  const amountText = (row: ReferralReward) => (
    row.basis === 'PERCENT' && Number(row.rewardAmount) === 0 && row.rewardStatus !== 'PAID' && row.rewardStatus !== 'REJECTED'
      ? t('growth.amountSetWhenPaid')
      : formatMoney(row.rewardAmount)
  );

  const payBody = (row: ReferralReward) => {
    const referrer = row.referrerName || row.code || '';
    const code = (codes.data?.results ?? []).find((c) => c.id === row.referralCode);
    if (row.basis === 'PERCENT') {
      return t('growth.markPaidBodyPercent', { referrer, value: String(Number(code?.rewardValue ?? 0)) });
    }
    return t('growth.markPaidBodyFlat', { referrer, amount: formatMoney(row.rewardAmount) });
  };

  const valueBad = rewardValueProblem(rewardType, rewardValue || '0');
  const empty = !board.isLoading && !rewards.isLoading && !board.isError && !rewards.isError
    && (board.data ?? []).length === 0 && (rewards.data?.results ?? []).length === 0;

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.referrals')}</PageTitle>
      {isManager ? (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
          <CustomerField value={customer} onChange={setCustomer} />
          <TextField select size="small" label={t('growth.rewardType')} value={rewardType} onChange={(e) => setRewardType(e.target.value)} sx={{ minWidth: 140 }}>
            <MenuItem value="FLAT">{enumLabel('rewardType', 'FLAT')}</MenuItem>
            <MenuItem value="PERCENT">{enumLabel('rewardType', 'PERCENT')}</MenuItem>
          </TextField>
          <TextField
            size="small"
            label={t('growth.rewardValue')}
            value={rewardValue}
            error={valueBad}
            helperText={valueBad ? t('growth.rewardValueInvalid') : undefined}
            onChange={(e) => setRewardValue(e.target.value)}
          />
          <Button variant="contained" disabled={!customer || valueBad || issue.isPending || writesBlocked} onClick={() => issue.mutate()}>{t('growth.issueCode')}</Button>
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary">{t('growth.issueManagerOnly')}</Typography>
      )}
      {issued ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography>{t('growth.code')}: {issued}</Typography>
          <Button
            size="small"
            href={`https://wa.me/?text=${encodeURIComponent(
              shareUrl ? `${shareUrl}` : t('growth.shareReferralText', { code: issued }),
            )}`}
            target="_blank"
            rel="noopener"
          >
            WhatsApp
          </Button>
        </Stack>
      ) : null}
      {error ? <Typography color="error">{error}</Typography> : null}
      {notice ? <Typography variant="body2">{notice}</Typography> : null}
      {board.isLoading || rewards.isLoading || codes.isLoading ? <LoadingState /> : null}
      {board.isError ? <ErrorState message={getErrorMessage(board.error)} error={board.error} onRetry={() => void board.refetch()} /> : null}
      {rewards.isError ? <ErrorState message={getErrorMessage(rewards.error)} error={rewards.error} onRetry={() => void rewards.refetch()} /> : null}
      {codes.isError ? <ErrorState message={getErrorMessage(codes.error)} error={codes.error} onRetry={() => void codes.refetch()} /> : null}
      {empty ? <EmptyState description={t('cog.emptyReferrals')} /> : null}

      <Typography variant="subtitle2">{t('growth.referralCodes')}</Typography>
      {!codes.isLoading && !codes.isError && (codes.data?.results ?? []).length === 0 ? (
        <Typography variant="body2" color="text.secondary">{t('growth.noCodes')}</Typography>
      ) : null}
      {(codes.data?.results ?? []).length > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }} tabIndex={0} role="region" aria-label={t('common.scrollableTable')}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('growth.code')}</TableCell>
                <TableCell>{t('growth.referrer')}</TableCell>
                <TableCell>{t('growth.rewardType')}</TableCell>
                <TableCell align="right">{t('growth.codeUses')}</TableCell>
                <TableCell align="right">{t('growth.rewardsEarned')}</TableCell>
                <TableCell>{t('common.status')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(codes.data?.results ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.code}</TableCell>
                  <TableCell>{row.referrerName || '—'}</TableCell>
                  <TableCell>
                    {enumLabel('rewardType', row.rewardType)}
                    {' · '}
                    {row.rewardType === 'PERCENT' ? `${Number(row.rewardValue)}%` : formatMoney(row.rewardValue)}
                  </TableCell>
                  <TableCell align="right">{row.uses}</TableCell>
                  <TableCell align="right">{row.rewardsEarned}</TableCell>
                  <TableCell>{row.active ? t('growth.codeActive') : t('growth.codeDeactivated')}</TableCell>
                  <TableCell align="right">
                    {row.active ? (
                      <Button size="small" onClick={() => void copyLink(row.code)}>{t('growth.copyLink')}</Button>
                    ) : null}
                    {row.active && canDecide ? (
                      <Button size="small" color="warning" onClick={() => setCodeTarget(row)}>{t('growth.deactivate')}</Button>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <Typography variant="subtitle2">{t('growth.leaderboard')}</Typography>
      {(board.data ?? []).map((row) => (
        <Typography key={row.code}>{row.code} · {row.referrerName || row.referrerType} · {formatMoney(row.approvedTotal)}</Typography>
      ))}

      <Typography variant="subtitle2">{t('growth.rewards')}</Typography>
      <Typography variant="caption" color="text.secondary">{t('growth.markPaidHint')}</Typography>
      {(rewards.data?.results ?? []).length > 0 ? (
        <Paper variant="outlined" sx={{ overflow: 'auto' }} tabIndex={0} role="region" aria-label={t('common.scrollableTable')}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('growth.dealColumn')}</TableCell>
                <TableCell>{t('growth.referrer')}</TableCell>
                <TableCell align="right">{t('growth.amountColumn')}</TableCell>
                <TableCell>{t('growth.rewardStatusLabel')}</TableCell>
                <TableCell align="right">{t('common.actions')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(rewards.data?.results ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    {row.customerName || row.leadName || '—'}
                    <Typography variant="caption" display="block" color="text.secondary">{row.opportunityTitle}</Typography>
                  </TableCell>
                  <TableCell>
                    {row.referrerName || '—'}
                    <Typography variant="caption" display="block" color="text.secondary">{row.code}</Typography>
                  </TableCell>
                  <TableCell align="right">{amountText(row)}</TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                      <Chip size="small" label={enumLabel('rewardStatus', row.rewardStatus)} />
                      {row.reviewNote === 'existing_customer' ? (
                        <Chip size="small" color="warning" label={t('growth.existingCustomerWarning')} />
                      ) : null}
                    </Stack>
                    {row.rejectionReason === 'self_referral' ? (
                      <Typography variant="caption" display="block">{t('growth.selfReferralRejected')}</Typography>
                    ) : null}
                  </TableCell>
                  <TableCell align="right">
                    {canDecide && row.rewardStatus === 'PENDING' ? (
                      <>
                        <Button size="small" onClick={() => decide.mutate({ id: row.id, decision: 'approve' })}>{t('growth.approve')}</Button>
                        <Button size="small" onClick={() => decide.mutate({ id: row.id, decision: 'reject' })}>{t('growth.reject')}</Button>
                      </>
                    ) : null}
                    {canDecide && row.rewardStatus === 'APPROVED' ? (
                      <>
                        <Button size="small" onClick={() => setPayTarget(row)}>{t('growth.markPaid')}</Button>
                        <Button size="small" color="warning" onClick={() => setReverseTarget(row)}>{t('growth.reverse')}</Button>
                      </>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      ) : null}

      <ConfirmDialog
        open={payTarget !== null}
        title={t('growth.markPaidTitle')}
        body={payTarget ? payBody(payTarget) : ''}
        confirming={decide.isPending}
        onClose={() => setPayTarget(null)}
        onConfirm={() => {
          if (payTarget) decide.mutate({ id: payTarget.id, decision: 'mark-paid' });
        }}
      />
      <ConfirmDialog
        open={reverseTarget !== null}
        title={t('growth.reverseTitle')}
        body={t('growth.reverseBody')}
        confirmColor="warning"
        confirming={decide.isPending}
        onClose={() => setReverseTarget(null)}
        onConfirm={() => {
          if (reverseTarget) decide.mutate({ id: reverseTarget.id, decision: 'reverse' });
        }}
      />
      <ConfirmDialog
        open={codeTarget !== null}
        title={t('growth.deactivateTitle')}
        body={t('growth.deactivateBody', { code: codeTarget?.code ?? '' })}
        confirmColor="warning"
        confirming={deactivate.isPending}
        onClose={() => setCodeTarget(null)}
        onConfirm={() => {
          if (codeTarget) deactivate.mutate(codeTarget.id);
        }}
      />
    </Stack>
  );
}
