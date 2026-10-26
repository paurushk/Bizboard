import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import { styled } from '@mui/material/styles';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { HonestyBanner } from '@/components/HonestyBanner';
import { EmptyState } from '@/components/PageState';
import { t, useLocale } from '@/i18n';
import { FAQ_CATEGORIES, FAQ_ITEMS, type FaqItem } from './faqContent';
import { FAQ_CATEGORIES_HI, FAQ_HI } from './faqContent.hi';
import { HelpRichText } from './HelpRichText';

function matches(item: FaqItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  // Hindi words match in either language (BB-100 F4).
  const hi = FAQ_HI[item.id];
  const hay = [item.id, item.question, item.category, ...(item.keywords ?? []), hi?.question ?? '', ...(hi?.keywords ?? [])]
    .join(' ')
    .toLowerCase();
  return needle.split(/\s+/).every((word) => hay.includes(word));
}

/** v0 Help page — flag-off render path. Do not change unless v0 FAQ copy changes. */
export function HelpPageV0() {
  const location = useLocation();
  const hindi = useLocale() === 'hi';
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  // Deep link: /help#unit-conversion-rate opens that entry and scrolls to it.
  const hash = location.hash.replace('#', '');
  const deepLink = hash && FAQ_ITEMS.some((item) => item.id === hash) ? hash : null;
  const [seenDeepLink, setSeenDeepLink] = useState<string | null>(null);
  if (seenDeepLink !== deepLink) {
    setSeenDeepLink(deepLink);
    if (deepLink) setExpanded(deepLink);
  }
  useEffect(() => {
    if (!deepLink) return;
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(deepLink)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [deepLink]);

  const onToggle = useCallback((id: string, isOpen: boolean) => setExpanded(isOpen ? id : null), []);

  const grouped = useMemo(() => {
    const visible = FAQ_ITEMS.filter((item) => matches(item, query));
    return FAQ_CATEGORIES.map((category) => ({
      category,
      items: visible.filter((item) => item.category === category),
    })).filter((group) => group.items.length > 0);
  }, [query]);

  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">{t('help.title')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('help.subtitle')}
      </Typography>
      <HonestyBanner messageKey="honesty.mobileWebview" />
      {hindi ? (
        <Typography variant="caption" color="text.secondary">{t('help.hindiDraftNote')}</Typography>
      ) : null}
      <TextField
        label={t('help.searchLabel')}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        fullWidth
        size="small"
        sx={{ maxWidth: 480 }}
      />
      {grouped.length === 0 ? (
        <EmptyState description={t('help.noResults')} />
      ) : (
        grouped.map((group) => (
          <Stack key={group.category} spacing={1}>
            <Typography variant="overline" color="text.secondary">
              {hindi ? FAQ_CATEGORIES_HI[group.category] ?? group.category : group.category}
            </Typography>
            <Paper variant="outlined">
              {group.items.map((item) => (
                <FaqEntry
                  key={item.id}
                  item={item}
                  hindi={hindi}
                  open={expanded === item.id}
                  onToggle={onToggle}
                />
              ))}
            </Paper>
          </Stack>
        ))
      )}
    </Stack>
  );
}

// Styles defined once, not per entry: ~280 per-entry `sx` objects were most of the render time.
const EntryRow = styled('div')(({ theme }) => ({
  '&:not(:last-of-type)': { borderBottom: `1px solid ${theme.palette.divider}` },
}));

const QuestionButton = styled('button')(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: theme.spacing(1),
  width: '100%',
  minHeight: 48,
  padding: theme.spacing(1.5, 2),
  border: 0,
  background: 'transparent',
  color: theme.palette.text.primary,
  font: 'inherit',
  fontWeight: 600,
  textAlign: 'left',
  cursor: 'pointer',
  '&:hover': { background: theme.palette.action.hover },
  '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: -2 },
}));

const Chevron = styled(ExpandMoreIcon)(({ theme }) => ({
  flexShrink: 0,
  color: theme.palette.text.secondary,
  '[aria-expanded="true"] > &': { transform: 'rotate(180deg)' },
}));

/**
 * One question and its answer. BB-100: ~280 MUI Accordions (each with a ripple button and a
 * collapse transition) kept /help blank for seconds on a full load; a plain disclosure button
 * renders the same list in a fraction of the time. The answer mounts only when open.
 */
const FaqEntry = memo(function FaqEntry({
  item,
  hindi,
  open,
  onToggle,
}: {
  item: FaqItem;
  hindi: boolean;
  open: boolean;
  onToggle: (id: string, open: boolean) => void;
}) {
  const answerId = `${item.id}-answer`;
  // BB-100 F4: the Hindi draft where there is one; the English entry otherwise.
  const hi = hindi ? FAQ_HI[item.id] : undefined;
  return (
    <EntryRow>
      <QuestionButton
        type="button"
        id={item.id}
        aria-expanded={open}
        aria-controls={answerId}
        onClick={() => onToggle(item.id, !open)}
      >
        <span>{hi?.question ?? item.question}</span>
        <Chevron aria-hidden />
      </QuestionButton>
      {open ? (
        <Box id={answerId} role="region" aria-labelledby={item.id} sx={{ px: 2, pb: 2 }}>
          {hi ? (
            <Stack spacing={1.5}>
              {hi.paragraphs.map((text) => (
                <HelpRichText key={text} text={text} />
              ))}
            </Stack>
          ) : (
            item.answer
          )}
        </Box>
      ) : null}
    </EntryRow>
  );
});
