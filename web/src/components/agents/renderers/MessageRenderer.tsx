import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import { t } from '@/i18n';
import type { RendererProps } from './types';

type Variants = Record<string, string>;

const LANGUAGES = ['en', 'hi'] as const;
const TONES = ['polite', 'firm'] as const;

/**
 * Editable text with copy and a WhatsApp share link. When the draft carries pre-written variants
 * (language x tone), the user can switch wording without another round trip. Used by reminders and
 * supplier queries.
 */
export function MessageRenderer({ value, onChange, disabled }: RendererProps) {
  const text = typeof value.text === 'string' ? value.text : '';
  const variants: Variants | null =
    value.variants && typeof value.variants === 'object' ? (value.variants as Variants) : null;
  const language = typeof value.language === 'string' ? value.language : 'en';
  const tone = typeof value.tone === 'string' ? value.tone : 'polite';
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function pick(nextLanguage: string, nextTone: string) {
    const next = variants?.[`${nextLanguage}:${nextTone}`];
    if (next === undefined) return;
    onChange({ ...value, text: next, language: nextLanguage, tone: nextTone });
  }

  return (
    <Stack spacing={1.5}>
      {variants ? (
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
          <Stack spacing={0.5}>
            <Typography variant="caption" color="text.secondary">{t('agents.variants.language')}</Typography>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={language}
              disabled={disabled}
              aria-label={t('agents.variants.language')}
              onChange={(_e, next: string | null) => next && pick(next, tone)}
            >
              {LANGUAGES.map((l) => (
                <ToggleButton key={l} value={l}>{t(`agents.variants.${l}`)}</ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Stack>
          <Stack spacing={0.5}>
            <Typography variant="caption" color="text.secondary">{t('agents.variants.tone')}</Typography>
            <ToggleButtonGroup
              size="small"
              exclusive
              value={tone}
              disabled={disabled}
              aria-label={t('agents.variants.tone')}
              onChange={(_e, next: string | null) => next && pick(language, next)}
            >
              {TONES.map((x) => (
                <ToggleButton key={x} value={x}>{t(`agents.variants.${x}`)}</ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Stack>
        </Stack>
      ) : null}
      <TextField
        label={t('agents.message.label')}
        value={text}
        onChange={(e) => onChange({ ...value, text: e.target.value })}
        multiline
        minRows={5}
        fullWidth
        disabled={disabled}
        inputProps={{ maxLength: 2000 }}
      />
      <Stack direction="row" spacing={1}>
        <Button size="small" variant="outlined" onClick={copy} disabled={!text}>
          {copied ? t('agents.message.copied') : t('agents.message.copy')}
        </Button>
        <Button
          size="small"
          variant="outlined"
          component="a"
          href={`https://wa.me/?text=${encodeURIComponent(text)}`}
          target="_blank"
          rel="noopener noreferrer"
          disabled={!text}
        >
          {t('agents.message.share')}
        </Button>
      </Stack>
    </Stack>
  );
}
