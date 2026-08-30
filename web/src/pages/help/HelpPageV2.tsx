import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import Chip from '@mui/material/Chip';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { Link as RouterLink } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { isOwner } from '@/utils/permissions';
import { EmptyState } from '@/components/PageState';
import { t } from '@/i18n';
import { HELP_EVENTS, trackHelpEvent } from './analytics';
import { DiagnosisPicker } from './DiagnosisPicker';
import { HelpFeedbackForm } from './HelpFeedbackForm';
import { HELP_CATEGORIES, HELP_INTENTS, getHelpIntent } from './intents';
import { IntentBody } from './IntentBody';
import { resolveHelpQuery } from './resolver';
import type { HelpContext, HelpOpenSource } from './types';

const OPEN_SOURCES: HelpOpenSource[] = ['nav', 'field', 'error', 'empty', 'search', 'assistant'];

function DiagnosticBlock({
  intent,
  context,
  leafParam,
}: {
  intent: NonNullable<ReturnType<typeof getHelpIntent>>;
  context: HelpContext;
  leafParam?: string;
}) {
  const skipParentBody = Boolean(leafParam);
  return (
    <>
      {!skipParentBody ? <IntentBody intent={intent} context={context} hideNextStep /> : null}
      <DiagnosisPicker intent={intent} context={context} initialLeafId={leafParam} />
    </>
  );
}

export function HelpPageV2() {
  const [params, setParams] = useSearchParams();
  const qParam = params.get('q') ?? '';
  const intentParam = params.get('intent') ?? '';
  const sourceParam = params.get('source');
  const invoiceId = params.get('invoiceId') ?? undefined;
  const leafParam = params.get('leaf') ?? undefined;
  const { user } = useAuth();
  const staff = Boolean(user?.isStaff);
  const showHealth = isOwner(user?.role ?? 'VIEWER') || staff;
  const [query, setQuery] = useState(qParam);
  const context: HelpContext = {
    invoiceId,
    from: params.get('from') ?? undefined,
    leaf: leafParam,
  };

  useEffect(() => {
    setQuery(qParam);
  }, [qParam]);

  useEffect(() => {
    const source: HelpOpenSource =
      sourceParam && OPEN_SOURCES.includes(sourceParam as HelpOpenSource)
        ? (sourceParam as HelpOpenSource)
        : 'nav';
    trackHelpEvent(HELP_EVENTS.OPEN, { source, intentId: intentParam || undefined });
  }, [intentParam, sourceParam]);

  const resolved = useMemo(() => resolveHelpQuery(query), [query]);

  useEffect(() => {
    if (!query.trim()) return undefined;
    const timer = window.setTimeout(() => {
      trackHelpEvent(HELP_EVENTS.SEARCH, {
        query,
        result_count: resolved.hits.length,
        state: resolved.state,
        intentId: resolved.intent?.intentId,
      });
    }, 400);
    return () => window.clearTimeout(timer);
  }, [query, resolved.hits.length, resolved.state, resolved.intent?.intentId]);

  const pinned = getHelpIntent(intentParam);
  const showPinned = Boolean(pinned) && !query.trim();
  const activeIntent = showPinned ? pinned : resolved.intent;
  const isType6 = Boolean(activeIntent?.type === 6 && activeIntent.diagnosis?.length);

  const onSearch = (value: string) => {
    setQuery(value);
    const next = new URLSearchParams(params);
    if (value) next.set('q', value);
    else next.delete('q');
    if (value) next.delete('intent');
    setParams(next, { replace: true });
  };

  const openIntent = (id: string) => {
    const next = new URLSearchParams(params);
    next.set('intent', id);
    next.delete('q');
    setQuery('');
    setParams(next);
  };

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('help.title')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('help.subtitleV2')}
      </Typography>
      <TextField
        label={t('help.searchLabelV2')}
        value={query}
        onChange={(e) => onSearch(e.target.value)}
        fullWidth
        size="small"
        sx={{ maxWidth: 560 }}
      />

      {showPinned && activeIntent ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {activeIntent.canonicalQuestion}
          </Typography>
          {isType6 ? (
            <DiagnosticBlock intent={activeIntent} context={context} leafParam={leafParam} />
          ) : (
            <IntentBody intent={activeIntent} context={context} />
          )}
          <HelpFeedbackForm intentId={activeIntent.intentId} query={query} surface="page" />
        </Paper>
      ) : null}

      {!showPinned && query.trim() && resolved.state === 'confident' && activeIntent ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {activeIntent.canonicalQuestion}
          </Typography>
          <IntentBody intent={activeIntent} context={context} />
          <HelpFeedbackForm intentId={activeIntent.intentId} query={query} surface="page" />
        </Paper>
      ) : null}

      {!showPinned && query.trim() && resolved.state === 'diagnostic' && activeIntent ? (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            {activeIntent.canonicalQuestion}
          </Typography>
          {isType6 ? (
            <DiagnosticBlock intent={activeIntent} context={context} leafParam={leafParam} />
          ) : (
            <IntentBody intent={activeIntent} context={context} />
          )}
          <HelpFeedbackForm intentId={activeIntent.intentId} query={query} surface="page" />
        </Paper>
      ) : null}

      {!showPinned && query.trim() && resolved.state === 'ambiguous' ? (
        <Stack spacing={1}>
          <Typography variant="subtitle1">{t('help.whatTrying')}</Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {resolved.chips.map((chip) => (
              <Chip
                key={chip.id}
                label={chip.label}
                onClick={() => openIntent(chip.intentId)}
                clickable
              />
            ))}
          </Stack>
        </Stack>
      ) : null}

      {!showPinned && query.trim() && resolved.state === 'no-match' ? (
        <Stack spacing={1}>
          <EmptyState
            title={t('help.noResultsV2')}
            description={
              resolved.categoryHint
                ? t('help.startHereIn', { category: resolved.categoryHint })
                : t('help.startHere')
            }
          />
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {HELP_INTENTS.filter((i) => i.category === resolved.categoryHint)
              .slice(0, 4)
              .map((i) => (
                <Chip key={i.intentId} label={i.canonicalQuestion} onClick={() => openIntent(i.intentId)} clickable />
              ))}
          </Stack>
          <HelpFeedbackForm query={query} surface="no-match" captureOnly />
        </Stack>
      ) : null}

      {!query.trim() && !showPinned
        ? HELP_CATEGORIES.map((category) => {
            const items = HELP_INTENTS.filter((i) => i.category === category);
            if (!items.length) return null;
            return (
              <Stack key={category} spacing={1}>
                <Typography variant="overline" color="text.secondary">
                  {category}
                </Typography>
                <Paper variant="outlined">
                  {items.map((item) => (
                    <Button
                      key={item.intentId}
                      fullWidth
                      sx={{ justifyContent: 'flex-start', px: 2, py: 1.25, textTransform: 'none' }}
                      onClick={() => openIntent(item.intentId)}
                    >
                      {item.canonicalQuestion}
                    </Button>
                  ))}
                </Paper>
              </Stack>
            );
          })
        : null}

      {showHealth ? (
        <Button component={RouterLink} to="/settings/help" size="small" sx={{ alignSelf: 'flex-start' }}>
          {t('help.healthLink')}
        </Button>
      ) : null}
    </Stack>
  );
}
