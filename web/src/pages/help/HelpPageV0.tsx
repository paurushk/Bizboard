import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { EmptyState } from '@/components/PageState';
import { t } from '@/i18n';
import { FAQ_CATEGORIES, FAQ_ITEMS, type FaqItem } from './faqContent';

function matches(item: FaqItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const hay = [item.question, item.category, ...(item.keywords ?? [])].join(' ').toLowerCase();
  return needle.split(/\s+/).every((word) => hay.includes(word));
}

/** v0 Help page — flag-off render path. Do not change unless v0 FAQ copy changes. */
export function HelpPageV0() {
  const location = useLocation();
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);

  // Deep link: /help#unit-conversion-rate opens that entry and scrolls to it.
  useEffect(() => {
    const hash = location.hash.replace('#', '');
    if (hash && FAQ_ITEMS.some((item) => item.id === hash)) {
      setExpanded(hash);
      window.requestAnimationFrame(() => {
        document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  }, [location.hash]);

  const grouped = useMemo(() => {
    const visible = FAQ_ITEMS.filter((item) => matches(item, query));
    return FAQ_CATEGORIES.map((category) => ({
      category,
      items: visible.filter((item) => item.category === category),
    })).filter((group) => group.items.length > 0);
  }, [query]);

  return (
    <Stack spacing={2}>
      <Typography variant="h4">{t('help.title')}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t('help.subtitle')}
      </Typography>
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
              {group.category}
            </Typography>
            <Paper variant="outlined">
              {group.items.map((item) => (
                <Accordion
                  key={item.id}
                  disableGutters
                  expanded={expanded === item.id}
                  onChange={(_, isOpen) => setExpanded(isOpen ? item.id : null)}
                >
                  <AccordionSummary expandIcon={<ExpandMoreIcon />} id={item.id}>
                    <Typography fontWeight={600}>{item.question}</Typography>
                  </AccordionSummary>
                  <AccordionDetails>{item.answer}</AccordionDetails>
                </Accordion>
              ))}
            </Paper>
          </Stack>
        ))
      )}
    </Stack>
  );
}
