import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Drawer from '@mui/material/Drawer';
import Link from '@mui/material/Link';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { Link as RouterLink } from 'react-router-dom';
import { t } from '@/i18n';
import { formatMoney, toNumber } from '@/utils/money';
import type { PlanSummary } from './planningTypes';

interface Props {
  summary: PlanSummary | null;
  onClose: () => void;
}

const WHO: Record<string, string> = {
  none: 'routes.plan.who.none',
  owner: 'routes.plan.who.owner',
  manager: 'routes.plan.who.manager',
  any: 'routes.plan.who.any',
};

/**
 * Everything the planner knows about one order, so the dispatcher does not leave the planning table to
 * find out: who and where, what is on it and whether the stock is there, the bill, the customer's money
 * position (only for people who may see it) and every risk with who can accept it. Read-only.
 */
export function OrderDrawer({ summary, onClose }: Props) {
  return (
    <Drawer anchor="right" open={summary !== null} onClose={onClose} PaperProps={{ sx: { width: { xs: '100%', sm: 440 }, p: 2 } }}>
      {summary ? (
        <Stack spacing={1.5} data-testid="order-drawer">
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="h6" component="h2">{summary.number || `#${summary.order}`}</Typography>
            <Button onClick={onClose} sx={{ minHeight: 44 }}>{t('common.close')}</Button>
          </Stack>

          <Box>
            <Typography variant="subtitle2">{summary.customer.name}</Typography>
            {summary.customer.phone ? (
              <Link href={`tel:${summary.customer.phone}`} underline="hover">{summary.customer.phone}</Link>
            ) : (
              <Typography variant="body2" color="warning.main">{t('routes.noPhone')}</Typography>
            )}
            <Typography variant="body2" color={summary.deliveryAddress ? 'text.primary' : 'warning.main'}>
              {summary.deliveryAddress || t('routes.noAddress')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {[summary.customer.pincode, summary.customer.state].filter(Boolean).join(' · ')}
              {summary.customer.hasLocation === false ? ` · ${t('routes.plan.noLocation')}` : ''}
            </Typography>
          </Box>

          <Divider />
          <Typography variant="subtitle2">{t('routes.plan.items')}</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>{t('nav.products')}</TableCell>
                <TableCell align="right">{t('billing.qty')}</TableCell>
                <TableCell align="right">{t('routes.plan.inStock')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {summary.lines.map((line) => (
                <TableRow key={line.product}>
                  <TableCell>{line.name}</TableCell>
                  <TableCell align="right">{line.quantity} {line.unit}</TableCell>
                  <TableCell align="right" sx={{ color: Number(line.short) > 0 ? 'warning.main' : undefined }}>
                    {line.available == null ? '—' : line.available}
                    {Number(line.short) > 0 ? ` (${t('routes.plan.short', { n: line.short })})` : ''}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <Divider />
          <Typography variant="subtitle2">{t('routes.billLabel')}</Typography>
          <Typography variant="body2">
            {t('routes.orderTotal')}: <b>{formatMoney(toNumber(summary.grandTotal))}</b> · {t(`routes.bill.${summary.bill.billStatus}`)}
          </Typography>
          <Typography variant="body2">
            {summary.bill.onCredit
              ? t('routes.onCredit', { days: summary.bill.paymentTermsDays })
              : `${t('routes.toCollect')}: ${formatMoney(toNumber(summary.bill.amountToCollect))}`}
          </Typography>
          {summary.bill.invoices.map((inv) => (
            <Link key={inv.id} component={RouterLink} to={`/sales/history/${inv.id}`} underline="hover" variant="body2">
              {inv.number || `#${inv.id}`} · {formatMoney(toNumber(inv.grandTotal))}
              {toNumber(inv.balance) > 0 ? ` (${t('routes.plan.balance')} ${formatMoney(toNumber(inv.balance))})` : ''}
            </Link>
          ))}

          {summary.money ? (
            <>
              <Divider />
              <Typography variant="subtitle2">{t('routes.plan.customerMoney')}</Typography>
              <Typography variant="body2">
                {t('routes.plan.outstanding')}: {formatMoney(toNumber(summary.money.outstanding))} · {t('routes.plan.overdue')}:{' '}
                {formatMoney(toNumber(summary.money.overdue))}
              </Typography>
              {toNumber(summary.money.creditLimit) > 0 ? (
                <Typography variant="body2">
                  {t('routes.plan.creditLimit')}: {formatMoney(toNumber(summary.money.creditLimit))}
                  {summary.money.exposure != null ? ` · ${t('routes.plan.exposure')}: ${formatMoney(toNumber(summary.money.exposure))}` : ''}
                </Typography>
              ) : null}
            </>
          ) : null}

          <Divider />
          <Typography variant="subtitle2">{t('routes.plan.risks')}</Typography>
          {summary.risks.length === 0 ? <Typography variant="body2" color="text.secondary">{t('routes.plan.noRisks')}</Typography> : null}
          {summary.risks.map((r) => (
            <Alert key={r.code} severity={r.level === 'block' ? 'error' : r.level === 'warn' ? 'warning' : 'info'}>
              {r.message}
              {r.level !== 'info' ? (
                <Typography variant="caption" display="block">{t(WHO[r.override])}</Typography>
              ) : null}
            </Alert>
          ))}
        </Stack>
      ) : null}
    </Drawer>
  );
}
