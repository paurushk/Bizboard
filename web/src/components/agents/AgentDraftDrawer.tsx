import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  approveProposal,
  cancelProposal,
  editProposal,
  rejectProposal,
  retryProposal,
  type AgentProposal,
} from '@/api/agents';
import { t } from '@/i18n';
import { agentErrorText, isStaleOrExpired } from './errors';
import { EvidenceList } from './EvidenceList';
import { ProposalStatusBadge } from './ProposalStatusBadge';
import { ProposalBody } from './renderers';
import { isPayloadReady } from './renderers/ready';
import { isKnownRenderer } from './renderers/types';

type Props = {
  proposal: AgentProposal | null;
  open: boolean;
  onClose: () => void;
  /** Called after any change so a queue can advance (rapid triage). */
  onSettled?: (outcome: 'approved' | 'rejected' | 'cancelled' | 'edited') => void;
  hasNext?: boolean;
  hasPrevious?: boolean;
  onNext?: () => void;
  onPrevious?: () => void;
};

function shallowEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Generic review shell for any proposal kind. The body comes from the kind's renderer, so a new agent
 * needs no change here. Approve always sends the revision the user is looking at and a fresh
 * Idempotency-Key per attempt.
 */
export function AgentDraftDrawer(props: Props) {
  const { proposal, open, onClose } = props;
  return (
    <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 480 } } }}>
      {/* Keyed, so local edits reset whenever a different proposal, or a new revision of it, is shown. */}
      {proposal ? <DrawerBody key={`${proposal.id}:${proposal.revision}`} {...props} proposal={proposal} /> : null}
    </Drawer>
  );
}

function DrawerBody({
  proposal, open, onClose, onSettled, hasNext, hasPrevious, onNext, onPrevious,
}: Props & { proposal: AgentProposal }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState<Record<string, unknown>>(proposal.payload);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const dirty = useMemo(() => !shallowEqual(value, proposal.payload), [value, proposal]);
  const known = isKnownRenderer(proposal.renderer);
  const actionable = proposal.status === 'PENDING' || proposal.status === 'FAILED';
  const editable = actionable && proposal.canApprove && known;
  const ready = isPayloadReady(proposal.renderer, value);
  const injection = proposal.evidence.some((e) => e.type === 'injection_suspected');

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ['agents'] });
    void queryClient.invalidateQueries({ queryKey: ['attention'] });
  }

  function fail(e: unknown) {
    setError(agentErrorText(e));
    if (isStaleOrExpired(e)) refresh();
  }

  const save = useMutation({
    mutationFn: () => editProposal(proposal.id, value, proposal.revision),
    onSuccess: () => {
      setError(null);
      refresh();
      onSettled?.('edited');
    },
    onError: fail,
  });

  const approve = useMutation({
    // A fresh key per click is generated inside approveProposal.
    mutationFn: () => (proposal.status === 'FAILED' && !dirty ? retryProposal(proposal.id, proposal.revision) : approveProposal(proposal.id, proposal.revision)),
    onSuccess: () => {
      setError(null);
      refresh();
      onSettled?.('approved');
    },
    onError: fail,
  });

  const reject = useMutation({
    mutationFn: () => rejectProposal(proposal.id, reason),
    onSuccess: () => {
      refresh();
      onSettled?.('rejected');
    },
    onError: fail,
  });

  const cancel = useMutation({
    mutationFn: () => cancelProposal(proposal.id),
    onSuccess: () => {
      refresh();
      onSettled?.('cancelled');
    },
    onError: fail,
  });

  const busy = save.isPending || approve.isPending || reject.isPending || cancel.isPending;

  // Rapid triage: A approve, R reject, J next, K previous. Ignored while typing in a field.
  useEffect(() => {
    if (!open) return undefined;
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === 'j' && hasNext) onNext?.();
      else if (k === 'k' && hasPrevious) onPrevious?.();
      else if (k === 'a' && editable && ready && !dirty && !busy) approve.mutate();
      else if (k === 'r' && editable && !busy) setRejecting(true);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, hasNext, hasPrevious, editable, ready, dirty, busy, onNext, onPrevious, approve]);

  return (
        <Box sx={{ p: 2.5 }} role="dialog" aria-label={t('agents.drawer.title')}>
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6" component="h2">{proposal.title}</Typography>
              <ProposalStatusBadge status={proposal.status} />
            </Stack>

            {injection ? <Alert severity="warning">{t('agents.drawer.injection')}</Alert> : null}
            {error ? <Alert severity="error" role="alert">{error}</Alert> : null}
            {proposal.status === 'FAILED' && proposal.failureCode && !error ? (
              <Alert severity="error">{proposal.decisionNote || t('agents.errors.generic')}</Alert>
            ) : null}

            <Box aria-live="polite">
              <ProposalBody renderer={proposal.renderer} value={value} onChange={setValue} disabled={!editable || busy} />
            </Box>
            {dirty ? <Alert severity="info">{t('agents.drawer.edited')}</Alert> : null}

            <Divider />
            <Typography variant="subtitle2" component="h3">{t('agents.drawer.evidence')}</Typography>
            <EvidenceList evidence={proposal.evidence} />

            {rejecting ? (
              <Stack spacing={1}>
                <TextField
                  label={t('agents.drawer.rejectReason')}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  size="small"
                  autoFocus
                />
                <Stack direction="row" spacing={1}>
                  <Button color="error" variant="contained" onClick={() => reject.mutate()} disabled={busy}>
                    {t('agents.drawer.reject')}
                  </Button>
                  <Button onClick={() => setRejecting(false)}>{t('agents.drawer.close')}</Button>
                </Stack>
              </Stack>
            ) : (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {editable && dirty ? (
                  <Button variant="contained" onClick={() => save.mutate()} disabled={busy}>
                    {t('agents.drawer.save')}
                  </Button>
                ) : null}
                {editable && !dirty ? (
                  <Button variant="contained" onClick={() => approve.mutate()} disabled={busy || !ready}>
                    {proposal.status === 'FAILED' ? t('agents.drawer.retry') : proposal.renderer === 'order' ? t('agents.order.create') : t('agents.drawer.approve')}
                  </Button>
                ) : null}
                {editable ? (
                  <Button color="error" onClick={() => setRejecting(true)} disabled={busy}>
                    {t('agents.drawer.reject')}
                  </Button>
                ) : null}
                {actionable && proposal.canApprove ? (
                  <Button onClick={() => cancel.mutate()} disabled={busy}>
                    {t('agents.drawer.cancel')}
                  </Button>
                ) : null}
                <Button onClick={onClose}>{t('agents.drawer.close')}</Button>
              </Stack>
            )}
            <Typography variant="caption" color="text.secondary">
              <RouterLink to="/help#agents-review-approve">{t('agents.drawer.learnMore')}</RouterLink>
            </Typography>
            {onNext || onPrevious ? (
              <Typography variant="caption" color="text.secondary">{t('agents.drawer.nextHint')}</Typography>
            ) : null}
          </Stack>
        </Box>
  );
}
