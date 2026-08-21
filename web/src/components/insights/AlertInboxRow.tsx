import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import TableCell from '@mui/material/TableCell';
import TableRow from '@mui/material/TableRow';
import { Link as RouterLink } from 'react-router-dom';
import { SeverityChip, type AlertSeverity } from './SeverityChip';

export type AlertInboxItem = {
  id?: number | string;
  code: string;
  severity: AlertSeverity;
  message: string;
  href?: string | null;
  ctaPath?: string | null;
  linkLabel?: string | null;
  documentType?: string;
  documentId?: number;
  number?: string;
};

export function resolveAlertHref(alert: AlertInboxItem): string | null {
  if (alert.href) return alert.href;
  if (alert.ctaPath) return alert.ctaPath;
  if (!alert.documentType || !alert.documentId) return null;
  if (alert.documentType === 'sales_invoice') return `/sales/history/${alert.documentId}`;
  if (alert.documentType === 'purchase_invoice') return `/purchases/history/${alert.documentId}`;
  if (alert.documentType === 'sales_credit_note') return `/sales/credit-notes/${alert.documentId}`;
  if (alert.documentType === 'sales_debit_note') return `/sales/debit-notes/${alert.documentId}`;
  if (alert.documentType === 'customer') return `/sales/customers`;
  if (alert.documentType === 'product') return `/inventory/stock`;
  return null;
}

export function AlertInboxRow({
  alert,
  onSnooze,
  snoozeLabel = 'Snooze 7d',
  showSnooze = false,
}: {
  alert: AlertInboxItem;
  onSnooze?: () => void;
  snoozeLabel?: string;
  showSnooze?: boolean;
}) {
  const href = resolveAlertHref(alert);
  return (
    <TableRow hover>
      <TableCell>
        <SeverityChip severity={alert.severity} />
      </TableCell>
      <TableCell sx={{ fontFamily: 'ui-monospace, monospace', fontSize: '0.8rem' }}>
        {alert.code}
      </TableCell>
      <TableCell>{alert.message}</TableCell>
      <TableCell>
        {href ? (
          <Link component={RouterLink} to={href}>
            {alert.linkLabel ?? alert.number ?? alert.documentId ?? 'Open'}
          </Link>
        ) : (
          (alert.number ?? '—')
        )}
      </TableCell>
      {showSnooze ? (
        <TableCell align="right">
          {onSnooze ? (
            <Button size="small" onClick={onSnooze}>
              {snoozeLabel}
            </Button>
          ) : null}
        </TableCell>
      ) : null}
    </TableRow>
  );
}
