import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Divider from '@mui/material/Divider';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getMoneyPosition, type MoneyAction, type MoneyPosition } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { t, useLocale } from '@/i18n';
import { moneyHref, moneyLinkHref } from '@/lib/moneyLinks';
import { MoneyOutlook } from '@/pages/money/MoneyOutlook';
import { MoneyTaxDues } from '@/pages/money/MoneyTaxDues';
import { AgeingList, StatCard, TileRow } from '@/pages/money/MoneyTiles';
import { formatMoney, toNumber } from '@/utils/money';

const ACTION_KEYS: Record<MoneyAction['kind'], string> = {
  chase_customer: 'money.actions.chaseCustomer',
  pay_supplier: 'money.actions.paySupplier',
  broken_promise: 'money.actions.brokenPromise',
  clear_cheque_in: 'money.actions.clearChequeIn',
  clear_cheque_out: 'money.actions.clearChequeOut',
};

const DAYS_KEYS: Record<MoneyAction['kind'], string> = {
  chase_customer: 'money.actions.daysOverdue',
  pay_supplier: 'money.actions.daysOverdue',
  broken_promise: 'money.actions.daysPastPromise',
  clear_cheque_in: 'money.actions.daysSinceEntry',
  clear_cheque_out: 'money.actions.daysSinceEntry',
};

const SECTION_LABELS: Record<string, string> = {
  basis: 'money.sections.basis',
  receivable: 'money.sections.receivable',
  payable: 'money.sections.payable',
  receivable_bills: 'money.sections.receivableBills',
  payable_bills: 'money.sections.payableBills',
  cash: 'money.sections.cash',
  money_in_bills: 'money.sections.receivableBills',
  money_out_bills: 'money.sections.payableBills',
  advances_received: 'money.sections.advancesReceived',
  cheques_pending: 'money.sections.chequesPending',
  cheques_bounced: 'money.sections.chequesBounced',
  tds_receivable: 'money.sections.tdsReceivable',
  promises: 'money.sections.promises',
  advances_paid: 'money.sections.advancesPaid',
  unmatched_bank: 'money.sections.unmatchedBank',
  gateway: 'money.sections.gateway',
  reconciliation: 'money.sections.reconciliation',
  actions: 'money.sections.actions',
};

function basisLabel(basis: 'GL' | 'DOCUMENTS' | undefined): string | undefined {
  if (!basis) return undefined;
  return basis === 'GL' ? t('money.basis.gl') : t('money.basis.documents');
}

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Paper variant="outlined" component="section" aria-label={title} sx={{ py: 1 }}>
      <Typography variant="h6" component="h2" sx={{ px: 1.5, pb: 0.5 }}>
        {title}
      </Typography>
      <Divider />
      <Stack divider={<Divider flexItem />} sx={{ pt: 0.5 }}>
        {children}
      </Stack>
    </Paper>
  );
}

function ReconciliationFooter({ data }: { data: MoneyPosition }) {
  const recon = data.reconciliation;
  if (!recon) return null;
  if (!recon.available) {
    return (
      <Typography variant="caption" color="text.secondary">
        {t('money.recon.booksOff')}
      </Typography>
    );
  }
  const drift = toNumber(recon.differenceReceivable) !== 0 || toNumber(recon.differencePayable) !== 0;
  return (
    <Alert severity={drift ? 'warning' : 'success'} variant="outlined">
      <Typography variant="body2">
        {t('money.recon.line', {
          receivable: formatMoney(recon.glReceivable),
          payable: formatMoney(recon.glPayable),
        })}
        {recon.basis === 'GL' && toNumber(recon.advancesReceived) > 0
          ? ` ${t('money.recon.afterAdvances', { amount: formatMoney(recon.advancesReceived) })}`
          : ''}
      </Typography>
      <Typography variant="body2">
        {drift
          ? t('money.recon.differs', {
              receivable: formatMoney(recon.differenceReceivable),
              payable: formatMoney(recon.differencePayable),
            })
          : t('money.recon.agrees')}{' '}
        <RouterLink to="/reports/books-health">{t('money.recon.open')}</RouterLink>
      </Typography>
    </Alert>
  );
}

export function MoneyHubPage() {
  useLocale();
  const query = useQuery({ queryKey: ['money-position'], queryFn: getMoneyPosition, retry: false });
  const data = query.data;

  if (query.isLoading) {
    return (
      <Stack spacing={2}>
        <PageTitle>{t('money.title')}</PageTitle>
        <LoadingState />
      </Stack>
    );
  }
  if (query.isError) {
    const off = isAxiosError(query.error) && query.error.response?.status === 404;
    return (
      <Stack spacing={2}>
        <PageTitle>{t('money.title')}</PageTitle>
        {off ? (
          <EmptyState description={t('money.off')} />
        ) : (
          <ErrorState message={getErrorMessage(query.error)} error={query.error} onRetry={() => void query.refetch()} />
        )}
      </Stack>
    );
  }
  if (!data) return null;

  const incoming = data.moneyIn;
  const outgoing = data.moneyOut;
  const hub = (route: string, params: Record<string, string> = {}) => moneyHref(route, params);
  const receivableBasis = basisLabel(data.basis.receivable);
  const partialNames = data.partial.map((name) => t(SECTION_LABELS[name] ?? 'money.sections.other'));

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline" useFlexGap flexWrap="wrap" spacing={1}>
        <PageTitle>{t('money.title')}</PageTitle>
        <Typography variant="body2" color="text.secondary">
          {t('money.asOf', { date: data.asOf })}
        </Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {t('money.intro')}
      </Typography>

      {partialNames.length > 0 ? (
        <Alert severity="warning" role="alert">
          {t('money.partial', { sections: partialNames.join(', ') })}
        </Alert>
      ) : null}

      <Box display="grid" gridTemplateColumns={{ xs: '1fr', sm: '1fr 1fr', md: 'repeat(4, 1fr)' }} gap={1.5}>
        <StatCard
          label={t('money.net.receivable')}
          value={data.net?.receivable}
          to={hub('/payments/collections')}
          badge={receivableBasis}
          unavailable={!data.net}
        />
        <StatCard
          label={t('money.net.payable')}
          value={data.net?.payable}
          to={hub('/purchases/history', { has_balance: '1' })}
          note={t('money.net.payableNote')}
          badge={basisLabel(data.basis.payable)}
          unavailable={!data.net}
        />
        <StatCard
          label={t('money.net.net')}
          value={data.net?.net}
          tone={data.net && toNumber(data.net.net) < 0 ? 'error' : undefined}
          note={t('money.net.netNote')}
          unavailable={!data.net}
        />
        <StatCard
          label={t('money.cash.title')}
          value={data.cash?.cleared}
          to={hub('/reports/cash-book')}
          note={t('money.cash.note')}
          unavailable={!data.cash}
        />
      </Box>
      {data.cash && data.cash.byAccount.length > 0 ? (
        <Typography variant="caption" color="text.secondary">
          {data.cash.byAccount.map((account) => `${account.name}: ${formatMoney(account.balance)}`).join(' · ')}
        </Typography>
      ) : null}

      <Box display="grid" gridTemplateColumns={{ xs: '1fr', md: '1fr 1fr' }} gap={2} alignItems="start">
        <Column title={t('money.in.title')}>
          <TileRow
            label={t('money.in.overdue')}
            data={incoming.bills?.overdue}
            to={hub('/payments/collections', { due: 'overdue' })}
            tone="error"
          />
          <TileRow
            label={t('money.in.dueSoon')}
            data={incoming.bills?.dueSoon}
            to={hub('/payments/collections', { due: 'soon' })}
          />
          <TileRow
            label={t('money.in.promisesBroken')}
            data={incoming.promises?.broken}
            to={hub('/payments/collections', { promises: 'broken' })}
            tone="warning"
            hideWhenZero
          />
          <TileRow
            label={t('money.in.promisesDue')}
            data={incoming.promises?.due}
            to={hub('/payments/collections', { promises: 'due' })}
            hideWhenZero
          />
          <TileRow
            label={t('money.in.advances')}
            hint={t('money.in.advancesHint')}
            data={incoming.advances}
            to={hub('/sales/receipts', { advance: '1' })}
            tone="info"
          />
          <TileRow
            label={t('money.in.chequesPending')}
            hint={t('money.in.chequesPendingHint')}
            data={incoming.chequesPending}
            to={hub('/sales/receipts', { cheque_status: 'PENDING_CLEARANCE' })}
            tone="warning"
          />
          <TileRow
            label={t('money.in.chequesBounced', { days: incoming.chequesBounced?.windowDays ?? 30 })}
            hint={t('money.in.chequesBouncedHint')}
            data={incoming.chequesBounced}
            to={hub('/sales/receipts', { status: 'VOIDED', cheque_status: 'BOUNCED' })}
            tone="error"
            hideWhenZero
          />
          <TileRow
            label={t('money.in.tds')}
            hint={
              incoming.tdsReceivable && incoming.tdsReceivable.olderThan30Days > 0
                ? t('money.in.tdsOld', { count: incoming.tdsReceivable.olderThan30Days })
                : t('money.in.tdsHint')
            }
            data={incoming.tdsReceivable}
            to={hub('/reports/tds-receivable', { certificate: 'pending' })}
          />
          <TileRow
            label={t('money.in.unmatched')}
            hint={t('money.in.unmatchedHint')}
            data={incoming.unmatchedBankCredits}
            to={hub('/payments/reconciliation', { direction: 'credit' })}
          />
          <TileRow
            label={t('money.in.gateway')}
            hint={t('money.in.gatewayHint')}
            data={incoming.gatewayAwaitingBooks}
            to={hub('/payments/links')}
            tone="warning"
            hideWhenZero
          />
          <TileRow
            label={t('money.in.links')}
            data={incoming.paymentLinksOpen}
            to={hub('/payments/links', { status: 'open' })}
            hideWhenZero
          />
          {incoming.bills ? (
            <AgeingList
              ageing={incoming.bills.ageing}
              notOnABill={incoming.bills.notOnABill}
              to={hub('/payments/collections')}
              side={t('money.in.title')}
            />
          ) : null}
        </Column>

        <Column title={t('money.out.title')}>
          <TileRow
            label={t('money.out.overdue')}
            data={outgoing.bills?.overdue}
            to={hub('/purchases/history', { overdue: '1' })}
            tone="error"
          />
          <TileRow
            label={t('money.out.dueSoon')}
            data={outgoing.bills?.dueSoon}
            to={hub('/purchases/history', { due_soon: '1' })}
          />
          <TileRow
            label={t('money.out.advances')}
            hint={t('money.out.advancesHint')}
            data={outgoing.advancesPaid}
            to={hub('/purchases/payments', { advance: '1' })}
            tone="info"
          />
          <TileRow
            label={t('money.out.chequesIssued')}
            hint={t('money.out.chequesIssuedHint')}
            data={outgoing.chequesIssuedPending}
            to={hub('/purchases/payments', { cheque_status: 'PENDING_CLEARANCE' })}
            tone="warning"
          />
          <TileRow
            label={t('money.out.unmatched')}
            hint={t('money.out.unmatchedHint')}
            data={outgoing.unmatchedBankDebits}
            to={hub('/payments/reconciliation', { direction: 'debit' })}
          />
          <Typography variant="caption" color="text.secondary">
            {t('money.out.notCounted')}
          </Typography>
          {outgoing.bills ? (
            <AgeingList
              ageing={outgoing.bills.ageing}
              notOnABill={outgoing.bills.notOnABill}
              to={hub('/purchases/history', { has_balance: '1' })}
              side={t('money.out.title')}
            />
          ) : null}
        </Column>
      </Box>

      <ReconciliationFooter data={data} />

      <Paper variant="outlined" component="section" aria-labelledby="money-actions-title" sx={{ p: 2 }}>
        <Typography id="money-actions-title" variant="h6" component="h2">
          {t('money.actions.title')}
        </Typography>
        {data.actions && data.actions.length > 0 ? (
          <Box
            tabIndex={0}
            role="region"
            aria-label={`${t('common.scrollableTable')}: ${t('money.actions.title')}`}
            sx={{ overflow: 'auto', mt: 1 }}
          >
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>{t('money.actions.what')}</TableCell>
                  <TableCell>{t('money.actions.who')}</TableCell>
                  <TableCell align="right">{t('money.actions.howLong')}</TableCell>
                  <TableCell align="right">{t('common.amount')}</TableCell>
                  <TableCell align="right">{t('common.actions')}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.actions.map((action, index) => (
                  <TableRow key={`${action.kind}-${action.partyId}-${action.reference}-${index}`}>
                    <TableCell>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={t(ACTION_KEYS[action.kind])}
                        color={action.kind === 'chase_customer' || action.kind === 'pay_supplier' ? 'warning' : 'default'}
                      />
                    </TableCell>
                    <TableCell>
                      {action.partyName}
                      {action.reference ? ` · ${action.reference}` : ''}
                    </TableCell>
                    <TableCell align="right">{t(DAYS_KEYS[action.kind], { count: action.days })}</TableCell>
                    <TableCell align="right">{formatMoney(action.amount)}</TableCell>
                    <TableCell align="right">
                      <Button size="small" component={RouterLink} to={moneyLinkHref(action.link)}>
                        {t('money.actions.open')}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {data.actions === null ? t('money.unavailable') : t('money.actions.none')}
          </Typography>
        )}
      </Paper>

      <MoneyOutlook />
      <MoneyTaxDues />
    </Stack>
  );
}
