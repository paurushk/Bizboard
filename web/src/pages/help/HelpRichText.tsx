/* eslint-disable react-refresh/only-export-components -- resolveHelpLabel is a helper deliberately co-located with the renderer it supports */
import type { ReactNode } from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { t } from '@/i18n';

/** Bold inner text: `t:nav.gst` resolves to the i18n catalog (HR-8.2). */
export function resolveHelpLabel(inner: string): string {
  if (inner.startsWith('t:')) return t(inner.slice(2));
  return inner;
}

/** Renders **bold** (UI labels) and `code` (typed values) only. */
export function HelpRichText({
  text,
  variant = 'body2',
}: {
  text: string;
  variant?: 'body2' | 'body1' | 'caption';
}) {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(text.slice(last, match.index));
    }
    const token = match[0];
    if (token.startsWith('**')) {
      nodes.push(
        <Box component="strong" key={`b-${key}`} sx={{ fontWeight: 700 }}>
          {resolveHelpLabel(token.slice(2, -2))}
        </Box>,
      );
    } else {
      nodes.push(
        <Box
          component="code"
          key={`c-${key}`}
          sx={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.9em', px: 0.4 }}
        >
          {token.slice(1, -1)}
        </Box>,
      );
    }
    key += 1;
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return (
    <Typography variant={variant} component="div" sx={{ lineHeight: 1.7 }}>
      {nodes}
    </Typography>
  );
}
