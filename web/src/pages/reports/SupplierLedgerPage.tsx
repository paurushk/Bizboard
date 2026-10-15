import { useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import DownloadIcon from '@mui/icons-material/Download';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';
import PrintIcon from '@mui/icons-material/Print';
import { useQuery } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getSupplierLedger } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { useSupplierSearch } from '@/hooks/usePartySearch';
import { t } from '@/i18n';
import type { LedgerEntry, Supplier } from '@/types/domain';
import { ledgerEntryPath } from './ledgerLinks';
import { toCsv } from '@/utils/csv';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';

function downloadLedgerCsv(supplierName: string, opening: number | null, entries: LedgerEntry[]): void {
  const rows: unknown[][] = [
    [
      t('common.date'),
      t('sweep2.typeText'),
      t('common.number'),
      t('reports.ledgerColReduces'),
      t('reports.ledgerColAdds'),
      t('reports.ledgerColBalance'),
    ],
  ];
  if (opening != null) rows.push(['', t('reports.ledgerOpening'), '', '', '', opening]);
  for (const e of entries) {
    rows.push([e.date, enumLabel('ledgerType', e.type), e.number ?? '', e.debit, e.credit, e.balance]);
  }
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `supplier-ledger-${supplierName.replace(/[^\w-]+/g, '_')}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export function SupplierLedgerPage() {
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  // Server-searched: a company with thousands of suppliers must not load them all to pick one.
  const supplierSearch = useSupplierSearch({ selected: supplier ?? undefined });
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const ledger = useQuery({
    queryKey: ['supplier-ledger', supplier?.id, dateFrom, dateTo],
    queryFn: () =>
      getSupplierLedger(supplier!.id, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      }),
    enabled: Boolean(supplier?.id),
  });

  const entries = useMemo(() => ledger.data?.entries ?? [], [ledger.data?.entries]);
  const opening = dateFrom && ledger.data?.openingBalance != null ? Number(ledger.data.openingBalance) : null;

  const handleWhatsAppShare = () => {
    if (!supplier || !ledger.data) return;
    let formattedPhone = (supplier.phone ?? '').replace(/\D/g, '');
    if (formattedPhone.length === 10) {
      formattedPhone = `91${formattedPhone}`;
    }
    const text = encodeURIComponent(
      t('reports.ledgerWhatsapp', { name: supplier.name, amount: formatMoney(ledger.data.outstanding) }),
    );
    const url = formattedPhone ? `https://wa.me/${formattedPhone}?text=${text}` : `https://wa.me/?text=${text}`;
    openShareUrl(url);
  };

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.supplierLedger')}</PageTitle>
      <Stack
        className="no-print"
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', md: 'center' }}
      >
        <Autocomplete
          options={supplierSearch.options}
          getOptionLabel={(o) => `${o.name}${o.phone ? ` (${o.phone})` : ''}`}
          isOptionEqualToValue={(o, v) => o.id === v.id}
          filterOptions={(opts) => opts}
          value={supplier}
          onChange={(_, v) => setSupplier(v)}
          onInputChange={(_, v) => supplierSearch.setQuery(v)}
          loading={supplierSearch.isFetching}
          sx={{ minWidth: 280, flex: 1 }}
          renderInput={(params) => (
            <TextField
              {...params}
              label={t('billing.supplier')}
              helperText={!supplierSearch.enabled ? t('common.typeToSearch') : undefined}
            />
          )}
        />
        <TextField
          type="date"
          size="small"
          label={t('common.dateFrom')}
          InputLabelProps={{ shrink: true }}
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
        />
        <TextField
          type="date"
          size="small"
          label={t('common.dateTo')}
          InputLabelProps={{ shrink: true }}
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
        />
        {supplier && ledger.data ? (
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<DownloadIcon />}
              onClick={() => downloadLedgerCsv(supplier.name, opening, entries)}
            >
              {t('reports.ledgerExportCsv')}
            </Button>
            <Button
              variant="outlined"
              color="success"
              startIcon={<WhatsAppIcon />}
              onClick={handleWhatsAppShare}
            >
              {t('reports.shareOnWhatsapp')}
            </Button>
            <Button
              variant="outlined"
              startIcon={<PrintIcon />}
              onClick={() => window.print()}
            >
              {t('common.print')}
            </Button>
          </Stack>
        ) : null}
      </Stack>

      {!supplier ? <EmptyState description={t('reports.ledgerSelectSupplier')} /> : null}
      {supplier && ledger.isLoading ? <LoadingState /> : null}
      {ledger.isError ? (
        <ErrorState message={ledger.error.message} error={ledger.error} onRetry={() => void ledger.refetch()} />
      ) : null}
      {ledger.data ? (
        <>
          <Paper sx={{ p: 2, bgcolor: 'background.paper', borderRadius: 1.5 }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
              <Typography variant="subtitle1">
                {supplier?.name} {supplier?.phone ? `· ${supplier.phone}` : ''}
              </Typography>
              <Typography variant="h6" color="primary.main">
                {t('dashboard.payables')}: <strong>{formatMoney(ledger.data.outstanding)}</strong>
              </Typography>
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
              {t('reports.ledgerHelp')}
            </Typography>
          </Paper>

          {entries.length === 0 && opening == null ? (
            <EmptyState description={t('reports.ledgerNoEntries')} />
          ) : (
            // F3-017: deliberately NOT virtualized — the Print button above
            // relies on every row being in the DOM (a windowed list would
            // only print the currently-visible rows).
            <Paper tabIndex={0} role="region" aria-label={t('common.scrollableTable')} sx={{ overflow: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>{t('common.date')}</TableCell>
                    <TableCell>{t('sweep2.typeText')}</TableCell>
                    <TableCell>{t('common.number')}</TableCell>
                    <TableCell align="right">{t('reports.ledgerColReduces')}</TableCell>
                    <TableCell align="right">{t('reports.ledgerColAdds')}</TableCell>
                    <TableCell align="right">{t('reports.ledgerColBalance')}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {opening != null ? (
                    <TableRow>
                      <TableCell>{dateFrom}</TableCell>
                      <TableCell colSpan={4}>
                        <em>{t('reports.ledgerOpening')}</em>
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        {formatMoney(opening)}
                      </TableCell>
                    </TableRow>
                  ) : null}
                  {entries.map((e, idx) => {
                    const path = ledgerEntryPath(e);
                    return (
                      <TableRow key={`${e.date}-${e.number}-${idx}`}>
                        <TableCell>{e.date}</TableCell>
                        <TableCell>{enumLabel('ledgerType', e.type)}</TableCell>
                        <TableCell>
                          {path ? (
                            <Link
                              component={RouterLink}
                              to={path}
                              aria-label={t('reports.ledgerOpenEntryFor', { number: e.number || e.type })}
                            >
                              {e.number ?? t('reports.ledgerOpenEntry')}
                            </Link>
                          ) : (
                            (e.number ?? '—')
                          )}
                          {e.jvNumber && e.jvNumber !== e.number ? (
                            <Typography variant="caption" display="block" color="text.secondary">
                              {e.jvNumber}
                            </Typography>
                          ) : null}
                        </TableCell>
                        <TableCell align="right" sx={{ color: Number(e.debit) > 0 ? 'success.main' : 'text.secondary' }}>
                          {formatMoney(e.debit)}
                        </TableCell>
                        <TableCell align="right" sx={{ color: Number(e.credit) > 0 ? 'text.primary' : 'text.secondary', fontWeight: Number(e.credit) > 0 ? 600 : 400 }}>
                          {formatMoney(e.credit)}
                        </TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>
                          {formatMoney(e.balance)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Paper>
          )}
        </>
      ) : null}
    </Stack>
  );
}
