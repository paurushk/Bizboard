import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import CloseIcon from '@mui/icons-material/Close';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import HelpOutlineIcon from '@mui/icons-material/HelpOutline';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import Stack from '@mui/material/Stack';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { getLocale, t } from '@/i18n';
import { HelpRichText } from '@/pages/help/HelpRichText';
import type { LocalizedText } from '@/pages/help/types';
import { getContextHelpPage } from './catalog';
import { resolveContextHelpPage } from './routes';
import type { ContextHelpPage } from './types';

function pick(text: LocalizedText): { value: string; fallbackHi: boolean } {
  const locale = getLocale();
  if (locale === 'hi' && text.hi) return { value: text.hi, fallbackHi: false };
  if (locale === 'hi' && !text.hi) return { value: text.en, fallbackHi: true };
  return { value: text.en, fallbackHi: false };
}

function SectionList({ items }: { items: LocalizedText[] }) {
  return (
    <Box component="ul" sx={{ m: 0, pl: 2 }}>
      {items.map((item) => {
        const { value } = pick(item);
        return (
          <Box key={value} component="li" sx={{ display: 'list-item', mb: 0.75 }}>
            <HelpRichText text={value} />
          </Box>
        );
      })}
    </Box>
  );
}

function HelpSection({
  id,
  title,
  defaultExpanded,
  children,
}: {
  id: string;
  title: string;
  defaultExpanded?: boolean;
  children: ReactNode;
}) {
  return (
    <Accordion
      defaultExpanded={defaultExpanded}
      disableGutters
      elevation={0}
      square
      sx={{
        '&:before': { display: 'none' },
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: 'transparent',
      }}
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />} aria-controls={`${id}-content`} id={`${id}-header`}>
        <Typography variant="subtitle2">{title}</Typography>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>{children}</AccordionDetails>
    </Accordion>
  );
}

function ContextHelpBody({ page }: { page: ContextHelpPage }) {
  const title = pick(page.title);
  const summary = pick(page.summary);
  return (
    <Stack spacing={1.5}>
      {title.fallbackHi || summary.fallbackHi ? (
        <Typography variant="caption" color="text.secondary">
          {t('help.hindiSoon')}
        </Typography>
      ) : null}
      <div>
        <Typography variant="overline" color="text.secondary">
          {t('help.contextSummary')}
        </Typography>
        <HelpRichText text={summary.value} />
      </div>
      <HelpSection id="how" title={t('help.howItWorks')} defaultExpanded>
        <SectionList items={page.howItWorks} />
      </HelpSection>
      <HelpSection id="impact" title={t('help.businessImpact')}>
        <SectionList items={page.businessImpact} />
      </HelpSection>
      <HelpSection id="rules" title={t('help.keyRules')}>
        <SectionList items={page.keyRules} />
      </HelpSection>
      <HelpSection id="mistakes" title={t('help.commonMistakes')}>
        <SectionList items={page.commonMistakes} />
      </HelpSection>
      <HelpSection id="related" title={t('help.relatedPages')}>
        <List dense disablePadding>
          {page.relatedPages.map((rel) => (
            <ListItem key={rel.path} disableGutters>
              <Link component={RouterLink} to={rel.path} variant="body2">
                {t(rel.labelKey)}
              </Link>
            </ListItem>
          ))}
        </List>
      </HelpSection>
      <HelpSection id="next" title={t('help.nextActions')}>
        <SectionList items={page.nextActions} />
      </HelpSection>
      <Divider />
      <Typography variant="caption" color="text.secondary">
        {t('help.contextReadOnly')}
      </Typography>
      <Link component={RouterLink} to="/help" variant="body2">
        {t('help.moreFaqs')}
      </Link>
    </Stack>
  );
}

/**
 * Page-level Help (`?`). Read-only: opens a right drawer and never posts,
 * Completes, allocates, or changes routing by itself.
 */
export function ContextHelp({ page }: { page?: string }) {
  const location = useLocation();
  const pageId = page ?? resolveContextHelpPage(location.pathname);
  const content = getContextHelpPage(pageId);
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const drawerId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);

  if (!content) return null;

  const heading = pick(content.title).value;

  return (
    <>
      <Tooltip title={t('help.pageAria')}>
        <IconButton
          size="small"
          aria-label={t('help.pageAria')}
          aria-expanded={open}
          aria-controls={open ? drawerId : undefined}
          aria-haspopup="dialog"
          data-testid="context-help-trigger"
          onClick={() => setOpen(true)}
        >
          <HelpOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>
      <Drawer
        anchor="right"
        open={open}
      onClose={() => setOpen(false)}
      transitionDuration={0}
      ModalProps={{ keepMounted: false }}
        PaperProps={{
          id: drawerId,
          role: 'dialog',
          sx: { width: { xs: '100%', sm: 420 }, p: 2 },
          'aria-labelledby': titleId,
          'data-testid': 'context-help-drawer',
        }}
      >
        <Stack spacing={2} sx={{ height: '100%' }}>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
            <Typography id={titleId} variant="h6" component="h2">
              {heading}
            </Typography>
            <IconButton ref={closeRef} aria-label={t('common.close')} onClick={() => setOpen(false)}>
              <CloseIcon />
            </IconButton>
          </Stack>
          <Box sx={{ overflow: 'auto', pb: 2 }}>
            <ContextHelpBody page={content} />
          </Box>
        </Stack>
      </Drawer>
    </>
  );
}
