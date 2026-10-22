import Alert from '@mui/material/Alert';
import type { AgentRenderer } from '@/api/agents';
import { t } from '@/i18n';
import { ComparisonRenderer } from './ComparisonRenderer';
import { LinesRenderer } from './LinesRenderer';
import { MessageRenderer } from './MessageRenderer';
import { OrderRenderer } from './OrderRenderer';
import type { RendererProps } from './types';

/** Pick the body for a proposal kind. An unknown renderer is read-only with approve disabled (see drawer). */
export function ProposalBody({ renderer, ...props }: RendererProps & { renderer: AgentRenderer }) {
  switch (renderer) {
    case 'message':
      return <MessageRenderer {...props} />;
    case 'lines':
      return <LinesRenderer {...props} />;
    case 'comparison':
      return <ComparisonRenderer {...props} />;
    case 'order':
      return <OrderRenderer {...props} />;
    default:
      return <Alert severity="info">{t('agents.unknownRenderer')}</Alert>;
  }
}
