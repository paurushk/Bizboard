import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
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
import { DisclaimerBanner, PageHeader, useMaskedText } from '@/components/insights';
import { AiConsentOffScreen, useAiConsentOn } from '@/components/insights/AiConsentGate';
import { ErrorState, LoadingState } from '@/components/PageState';
import { t } from '@/i18n';
import { isHelpV2Enabled } from '@/config/features';
import type { AssistantConfirmResult, AssistantMessage } from '@/types/domain';
import { isAllowedShareUrl, safeAppPath } from '@/utils/safeUrl';

type Outcome = { kind: 'ok' | 'err' | 'share'; text?: string; shareLink?: string };
type Candidate = { customerId: number; customerName: string };

const SUGGESTIONS = () => [t('insights.suggestSales'), t('insights.suggestAging'), t('insights.suggestAlerts')];

function proposal(m: AssistantMessage) {
  const pa = m.proposedAction;
  if (!pa || typeof pa !== 'object') return null;
  return pa as Record<string, unknown>;
}

function outcomeFor(result: AssistantConfirmResult): Outcome {
  if (result.status === 'link_ready' || (result.status === 'failed' && result.shareLink)) {
    return {
      kind: 'share',
      shareLink: result.shareLink,
      text: result.status === 'failed' ? result.error : undefined,
    };
  }
  if (result.status === 'queued') return { kind: 'ok', text: t('insights.confirmQueued') };
  if (result.copied) return { kind: 'ok', text: t('insights.copiedOk') };
  return { kind: 'ok', text: t('insights.confirmSentOk') };
}

export function InsightsAssistantPage() {
  const mask = useMaskedText();
  const consentOn = useAiConsentOn();
  const qc = useQueryClient();
  const [threadId, setThreadId] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<number, Outcome>>({});
  const endRef = useRef<HTMLDivElement | null>(null);

  const threads = useQuery({
    queryKey: ['insights-threads'],
    queryFn: listAssistantThreads,
    enabled: consentOn,
  });

  const activeId = threadId ?? threads.data?.[0]?.id ?? null;

  const thread = useQuery({
    queryKey: ['insights-thread', activeId],
    queryFn: () => getAssistantThread(activeId!),
    enabled: consentOn && activeId != null,
  });

  const createThread = useMutation({
    mutationFn: () => createAssistantThread(),
    onSuccess: (th) => {
      setThreadId(th.id);
      void qc.invalidateQueries({ queryKey: ['insights-threads'] });
    },
  });

  // The first message creates a chat, so there is no extra "New chat" step to find.
  const send = useMutation({
    mutationFn: async ({ content, hint }: { content: string; hint?: { customerId: number; action: string } }) => {
      let id = activeId;
      if (id == null) {
        const th = await createAssistantThread();
        id = th.id;
        setThreadId(id);
      }
      await postAssistantMessage(id, content, hint);
      return id;
    },
    onMutate: ({ content }) => setPendingText(content),
    onSuccess: (id) => {
      setDraft('');
      void qc.invalidateQueries({ queryKey: ['insights-thread', id] });
      void qc.invalidateQueries({ queryKey: ['insights-threads'] });
    },
    onSettled: () => setPendingText(null),
  });

  const confirm = useMutation({
    mutationFn: (messageId: number) => confirmAssistantAction(messageId),
    onSuccess: (result, messageId) => {
      setOutcomes((prev) => ({ ...prev, [messageId]: outcomeFor(result) }));
      void qc.invalidateQueries({ queryKey: ['insights-thread', activeId] });
    },
    onError: (err, messageId) => {
      setOutcomes((prev) => ({ ...prev, [messageId]: { kind: 'err', text: getErrorMessage(err) } }));
      void qc.invalidateQueries({ queryKey: ['insights-thread', activeId] });
    },
  });

  const dismiss = useMutation({
    mutationFn: (messageId: number) => dismissAssistantAction(messageId),
    onSuccess: (_r, messageId) => {
      setOutcomes((prev) => {
        const next = { ...prev };
        delete next[messageId];
        return next;
      });
      void qc.invalidateQueries({ queryKey: ['insights-thread', activeId] });
    },
  });

  const messageCount = thread.data?.messages?.length ?? 0;
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messageCount, pendingText]);

  const WHY_RE = /\b(why|explain|kyu|kyun|kaise)\b/i;
  const helpWhyHint = isHelpV2Enabled() && WHY_RE.test(draft);

  if (!consentOn) return <AiConsentOffScreen title={t('nav.insightsAssistant')} />;

  const busy = confirm.isPending || dismiss.isPending;
  const submit = () => {
    const content = draft.trim();
    if (content && !send.isPending) send.mutate({ content });
  };
  const messages = thread.data?.messages ?? [];

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
      <DisclaimerBanner>{t('honesty.insightsNotBooks')}</DisclaimerBanner>
      <DisclaimerBanner>{t('insights.disclaimer')}</DisclaimerBanner>

      <Stack direction={{ xs: 'column-reverse', md: 'row' }} spacing={2} alignItems="stretch">
        <Paper variant="outlined" sx={{ p: 1.5, width: { md: 220 }, flexShrink: 0 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {t('sweep2.threads')}
          </Typography>
          {threads.isLoading ? <LoadingState /> : null}
          <Stack spacing={0.5}>
            {(threads.data ?? []).map((th) => (
              <Button
                key={th.id}
                size="small"
                variant={th.id === activeId ? 'contained' : 'text'}
                onClick={() => setThreadId(th.id)}
                sx={{ justifyContent: 'flex-start', textAlign: 'left' }}
              >
                {th.title && th.title !== 'Chat' ? th.title : t('insights.chatNumber', { id: th.id })}
              </Button>
            ))}
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, flex: 1, minHeight: 360 }}>
          {activeId != null && thread.isLoading ? (
            <LoadingState />
          ) : thread.isError ? (
            <ErrorState message={getErrorMessage(thread.error)} error={thread.error} onRetry={() => void thread.refetch()} />
          ) : (
            <Stack
              spacing={1.5}
              role="log"
              aria-live="polite"
              tabIndex={0}
              aria-label={t('nav.insightsAssistant')}
              sx={{ mb: 2, maxHeight: 420, overflow: 'auto' }}
            >
              {messages.length === 0 && pendingText == null ? (
                <Stack spacing={1}>
                  <Typography color="text.secondary">{t('sweep2.startNewChat')}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t('insights.tryAsking')}
                  </Typography>
                  <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                    {SUGGESTIONS().map((s) => (
                      <Chip key={s} label={s} clickable onClick={() => send.mutate({ content: s })} />
                    ))}
                  </Stack>
                </Stack>
              ) : null}
              {messages.map((m) => {
                const pa = proposal(m);
                const kind = pa ? String(pa.type ?? '') : '';
                const outcome = outcomes[m.id];
                const email = pa ? String(pa.email ?? '') : '';
                const phone = pa ? String(pa.phone ?? '') : '';
                const hasContact = Boolean(email || phone);
                return (
                  <Paper
                    key={m.id}
                    variant="outlined"
                    sx={{ p: 1.5, bgcolor: m.role === 'user' ? 'action.hover' : 'background.paper' }}
                  >
                    <Typography variant="caption" color="text.secondary">
                      {m.role === 'user' ? t('insights.roleUser') : t('insights.roleAssistant')}
                      {m.role === 'assistant' && m.toolName === 'ai' ? ` · ${t('insights.modeAi')}` : null}
                      {m.role === 'assistant' && m.toolName === 'basic' ? ` · ${t('insights.modeBasic')}` : null}
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {mask(m.content)}
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

                    {kind === 'clarify' ? (
                      <Stack spacing={0.5} sx={{ mt: 1 }}>
                        <Typography variant="caption">{t('insights.whichCustomer')}</Typography>
                        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                          {((pa?.candidates as Candidate[] | undefined) ?? []).map((c) => (
                            <Chip
                              key={c.customerId}
                              label={c.customerName}
                              clickable
                              disabled={send.isPending}
                              onClick={() =>
                                send.mutate({
                                  content: c.customerName,
                                  hint: { customerId: c.customerId, action: String(pa?.action ?? '') },
                                })
                              }
                            />
                          ))}
                        </Stack>
                      </Stack>
                    ) : null}

                    {kind === 'NAVIGATE' || kind === 'SHOW_REPORT' ? (
                      <Button
                        size="small"
                        variant="outlined"
                        sx={{ mt: 1 }}
                        component={RouterLink}
                        to={safeAppPath(String(pa?.path ?? '/'))}
                        onClick={() => confirm.mutate(m.id)}
                      >
                        {String(pa?.label ?? '') || t('insights.openAction')}
                      </Button>
                    ) : null}

                    {kind === 'send_reminder' || kind === 'copy_reminder' ? (
                      <Paper variant="outlined" sx={{ p: 1, mt: 1 }}>
                        <Typography variant="caption">{t('sweep2.proposedReminder')}</Typography>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {t('insights.reminderTo', { name: String(pa?.customerName ?? pa?.customer_name ?? '') })}
                        </Typography>
                        {kind === 'send_reminder' ? (
                          <Typography variant="caption" color={hasContact ? 'text.secondary' : 'error'} display="block">
                            {email
                              ? t('insights.viaEmail', { recipient: email })
                              : phone
                                ? t('insights.viaWhatsapp', { recipient: phone })
                                : t('insights.noContact')}
                          </Typography>
                        ) : null}
                        <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap', mt: 0.5 }}>
                          {mask(String(pa?.text ?? ''))}
                        </Typography>
                        <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                          <Button
                            size="small"
                            variant="contained"
                            disabled={busy || (kind === 'send_reminder' && !hasContact)}
                            onClick={() => confirm.mutate(m.id)}
                          >
                            {t('insights.confirmSend')}
                          </Button>
                          <Button size="small" variant="outlined" disabled={busy} onClick={() => dismiss.mutate(m.id)}>
                            {t('insights.dismiss')}
                          </Button>
                        </Stack>
                      </Paper>
                    ) : null}

                    {outcome?.kind === 'err' ? (
                      <Typography variant="caption" color="error" display="block" sx={{ mt: 1 }}>
                        {outcome.text}
                      </Typography>
                    ) : null}
                    {outcome?.kind === 'ok' ? (
                      <Typography variant="caption" color="success.main" display="block" sx={{ mt: 1 }}>
                        {outcome.text}
                      </Typography>
                    ) : null}
                    {outcome?.kind === 'share' && outcome.shareLink && isAllowedShareUrl(outcome.shareLink) ? (
                      <Typography variant="caption" component="div" sx={{ mt: 1 }}>
                        {t('common.whatsapp')}:{' '}
                        <Link href={outcome.shareLink} target="_blank" rel="noopener noreferrer">
                          {t('insights.confirmLink')}
                        </Link>
                        {outcome.text ? ` — ${outcome.text}` : null}
                      </Typography>
                    ) : null}
                  </Paper>
                );
              })}
              {pendingText != null ? (
                <>
                  <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'action.hover' }}>
                    <Typography variant="caption" color="text.secondary">
                      {t('insights.roleUser')}
                    </Typography>
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {pendingText}
                    </Typography>
                  </Paper>
                  <Typography variant="body2" color="text.secondary">
                    {t('insights.thinking')}
                  </Typography>
                </>
              ) : null}
              <div ref={endRef} />
            </Stack>
          )}

          <Stack direction="row" spacing={1}>
            <TextField
              fullWidth
              size="small"
              placeholder={t('insights.assistantPlaceholder')}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={send.isPending}
              onKeyDown={(e) => {
                // Enter while composing (Hindi / Hinglish input) confirms the word, it does not send.
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <Button variant="contained" disabled={!draft.trim() || send.isPending} onClick={submit}>
              {t('insights.sendMessage')}
            </Button>
          </Stack>
          {helpWhyHint ? (
            <Alert severity="info">
              <Link component={RouterLink} to={`/help?q=${encodeURIComponent(draft.trim())}&source=assistant`}>
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
