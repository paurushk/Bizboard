import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import {
  confirmAssistantAction,
  createAssistantThread,
  dismissAssistantAction,
  getAssistantThread,
  listAssistantThreads,
  postAssistantMessage,
} from '@/api/resources';
import { DisclaimerBanner, PageHeader } from '@/components/insights';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { isHelpV2Enabled } from '@/config/features';
import { isAllowedShareUrl, safeAppPath } from '@/utils/safeUrl';

export function InsightsAssistantPage() {
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [actionByMsg, setActionByMsg] = useState<
    Record<number, { status: 'ok' | 'err' | 'share'; detail?: string; shareLink?: string }>
  >({});

  const threads = useQuery({
    queryKey: ['insights-threads'],
    queryFn: listAssistantThreads,
  });

  const activeId = threadId ?? threads.data?.[0]?.id ?? null;

  const thread = useQuery({
    queryKey: ['insights-thread', activeId],
    queryFn: () => getAssistantThread(activeId!),
    enabled: activeId != null,
  });

  const createThread = useMutation({
    mutationFn: () => createAssistantThread(),
    onSuccess: (th) => {
      setThreadId(th.id);
      void qc.invalidateQueries({ queryKey: ['insights-threads'] });
    },
  });

  const send = useMutation({
    mutationFn: (content: string) => postAssistantMessage(activeId!, content),
    onSuccess: () => {
      setDraft('');
      void qc.invalidateQueries({ queryKey: ['insights-thread', activeId] });
    },
  });

  const confirm = useMutation({
    mutationFn: (messageId: number) => confirmAssistantAction(messageId),
    onSuccess: (result, messageId) => {
      if (result.requires_user_share && result.share_link) {
        setActionByMsg((prev) => ({
          ...prev,
          [messageId]: {
            status: 'share',
            shareLink: String(result.share_link),
          },
        }));
      } else {
        setActionByMsg((prev) => ({
          ...prev,
          [messageId]: { status: 'ok', detail: result.copied ? 'Copied' : 'Sent' },
        }));
      }
      void qc.invalidateQueries({ queryKey: ['insights-thread', activeId] });
    },
    onError: (err, messageId) => {
      setActionByMsg((prev) => ({
        ...prev,
        [messageId]: { status: 'err', detail: getErrorMessage(err) },
      }));
    },
  });

  const dismiss = useMutation({
    mutationFn: (messageId: number) => dismissAssistantAction(messageId),
    onSuccess: (_r, messageId) => {
      setActionByMsg((prev) => {
        const next = { ...prev };
        delete next[messageId];
        return next;
      });
      void qc.invalidateQueries({ queryKey: ['insights-thread', activeId] });
    },
  });

  const WHY_RE = /\b(why|explain|kyu|kyun|kaise)\b/i;
  const helpWhyHint = isHelpV2Enabled() && WHY_RE.test(draft);

  return (
    <Stack spacing={2}>
      <PageHeader
        title={t('nav.insightsAssistant')}
        actions={
          <Button variant="outlined" onClick={() => createThread.mutate()} disabled={createThread.isPending}>
            {t('insights.newThread')}
          </Button>
        }
      />
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="stretch">
        <Paper variant="outlined" sx={{ p: 1.5, width: { md: 220 }, flexShrink: 0 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            Threads
          </Typography>
          {threads.isLoading ? <LoadingState /> : null}
          <Stack spacing={0.5}>
            {(threads.data ?? []).map((th) => (
              <Button
                key={th.id}
                size="small"
                variant={th.id === activeId ? 'contained' : 'text'}
                onClick={() => setThreadId(th.id)}
                sx={{ justifyContent: 'flex-start' }}
              >
                {th.title || `Chat #${th.id}`}
              </Button>
            ))}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, flex: 1, minHeight: 360 }}>
          {!activeId ? (
            <Typography color="text.secondary">Start a new chat to begin.</Typography>
          ) : thread.isLoading ? (
            <LoadingState />
          ) : thread.isError ? (
            <ErrorState message={getErrorMessage(thread.error)} error={thread.error} onRetry={() => void thread.refetch()} />
          ) : (
            <Stack spacing={1.5} sx={{ mb: 2, maxHeight: 420, overflow: 'auto' }}>
              {(thread.data?.messages ?? []).map((m) => (
                <Paper
                  key={m.id}
                  variant="outlined"
                  sx={{
                    p: 1.5,
                    bgcolor: m.role === 'user' ? 'action.hover' : 'background.paper',
                  }}
                >
                  <Typography variant="caption" color="text.secondary">
                    {m.role}
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {m.content}
                  </Typography>
                  <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
                    {(m.citations ?? []).map((c, i) => (
                      <Chip
                        key={`${c.path}-${i}`}
                        size="small"
                        label={c.label}
                        component={RouterLink}
                        to={safeAppPath(c.path)}
                        clickable
                      />
                    ))}
                  </Stack>
                  {m.proposedAction && typeof m.proposedAction === 'object' && 'text' in m.proposedAction ? (
                    <Paper variant="outlined" sx={{ p: 1, mt: 1, bgcolor: 'grey.50' }}>
                      <Typography variant="caption">Proposed reminder (not sent)</Typography>
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                        {String((m.proposedAction as { text?: string }).text ?? '')}
                      </Typography>
                      <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                        <Button
                          size="small"
                          variant="contained"
                          disabled={confirm.isPending || dismiss.isPending}
                          onClick={() => confirm.mutate(m.id)}
                        >
                          {t('insights.confirmSend')}
                        </Button>
                        <Button
                          size="small"
                          variant="outlined"
                          disabled={confirm.isPending || dismiss.isPending}
                          onClick={() => dismiss.mutate(m.id)}
                        >
                          {t('insights.dismiss')}
                        </Button>
                      </Stack>
                      {actionByMsg[m.id]?.status === 'err' ? (
                        <Typography variant="caption" color="error">
                          {actionByMsg[m.id].detail}
                        </Typography>
                      ) : null}
                      {actionByMsg[m.id]?.status === 'ok' ? (
                        <Typography variant="caption" color="success.main">
                          {actionByMsg[m.id].detail}
                        </Typography>
                      ) : null}
                      {actionByMsg[m.id]?.status === 'share' &&
                      actionByMsg[m.id].shareLink &&
                      isAllowedShareUrl(actionByMsg[m.id].shareLink!) ? (
                        <Typography variant="caption" component="div" sx={{ mt: 0.5 }}>
                          {t('common.whatsapp')}:{' '}
                          <Link href={actionByMsg[m.id].shareLink} target="_blank" rel="noopener noreferrer">
                            Share link
                          </Link>
                        </Typography>
                      ) : null}
                    </Paper>
                  ) : null}
                  {!m.proposedAction &&
                  actionByMsg[m.id]?.status === 'share' &&
                  actionByMsg[m.id].shareLink &&
                  isAllowedShareUrl(actionByMsg[m.id].shareLink!) ? (
                    <Typography variant="caption" component="div" sx={{ mt: 1 }}>
                      {t('common.whatsapp')}:{' '}
                      <Link href={actionByMsg[m.id].shareLink!} target="_blank" rel="noopener noreferrer">
                        Share link
                      </Link>
                    </Typography>
                  ) : null}
                  {!m.proposedAction && actionByMsg[m.id]?.status === 'ok' ? (
                    <Typography variant="caption" color="success.main" sx={{ display: 'block', mt: 1 }}>
                      {actionByMsg[m.id].detail}
                    </Typography>
                  ) : null}
                </Paper>
              ))}
            </Stack>
          )}

          <Stack direction="row" spacing={1}>
            <TextField
              fullWidth
              size="small"
              placeholder={t('insights.assistantPlaceholder')}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={!activeId || send.isPending}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && draft.trim() && activeId) {
                  e.preventDefault();
                  send.mutate(draft.trim());
                }
              }}
            />
            <Button
              variant="contained"
              disabled={!activeId || !draft.trim() || send.isPending}
              onClick={() => send.mutate(draft.trim())}
            >
              {t('insights.sendMessage')}
            </Button>
          </Stack>
          {helpWhyHint ? (
            <Alert severity="info">
              <Link
                component={RouterLink}
                to={`/help?q=${encodeURIComponent(draft.trim())}&source=assistant`}
              >
                {t('help.assistantHint')}
              </Link>
            </Alert>
          ) : null}
          {send.isError ? <ErrorState message={getErrorMessage(send.error)} error={send.error} /> : null}
        </Paper>
      </Stack>
    </Stack>
  );
}
