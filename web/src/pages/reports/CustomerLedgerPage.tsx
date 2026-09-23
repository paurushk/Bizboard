import { useEffect, useMemo, useState } from 'react';
import Autocomplete from '@mui/material/Autocomplete';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import WhatsAppIcon from '@mui/icons-material/WhatsApp';
import PrintIcon from '@mui/icons-material/Print';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCompany, getCustomer, getCustomerLedgerTabs, downloadCustomerLedgerXlsx, updateCustomer } from '@/api/resources';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import {
  HistoryFilterBar,
  EMPTY_HISTORY_FILTERS,
  type HistoryFilters,
} from '@/components/HistoryFilterBar';
import { useCustomerSearch } from '@/hooks/usePartySearch';
import { PageTitle } from '@/contextHelp';
import { t } from '@/i18n';
import { activeCustomFieldDefs } from '@/pages/inventory/itemCustomFieldDefaults';
import type { Customer, ShippingAddress } from '@/types/domain';
import { formatMoney, toNumber } from '@/utils/money';
import { openShareUrl } from '@/utils/safeUrl';
import { triggerBlobDownload } from '@/utils/blob';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

export function CustomerLedgerPage() {
  const qc = useQueryClient();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const customerSearch = useCustomerSearch({ selected: customer });
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_HISTORY_FILTERS);
  const [tab, setTab] = useState(0);
  const [txnType, setTxnType] = useState('');
  const [txnStatus, setTxnStatus] = useState('');
  const [searchParams] = useSearchParams();
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    const id = searchParams.get('customer') || searchParams.get('customerId');
    if (!id || customer) return;
    let cancelled = false;
    getCustomer(id)
      .then((c) => {
        if (!cancelled) setCustomer(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [searchParams, customer]);

  const ledger = useQuery({
    queryKey: ['customer-ledger-tabs', customer?.id, filters.dateFrom, filters.dateTo, txnType, txnStatus],
    queryFn: () =>
      getCustomerLedgerTabs(customer!.id, {
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
        txn_type: txnType || undefined,
        status: txnStatus || undefined,
      }),
    enabled: Boolean(customer?.id),
  });

  const profile = (ledger.data?.profile ?? {}) as Record<string, unknown>;
  const kpis = (ledger.data?.kpis ?? {}) as Record<string, unknown>;
  const transactions = useMemo(
    () => (ledger.data?.transactions as Record<string, unknown>[]) ?? [],
    [ledger.data],
  );
  const statementEntries = useMemo(() => {
    const raw = ledger.data?.statement;
    if (Array.isArray(raw)) return raw as Record<string, unknown>[];
    if (raw && typeof raw === 'object') {
      return ((raw as { entries?: Record<string, unknown>[] }).entries) ?? [];
    }
    return [];
  }, [ledger.data]);
  const statementOutstanding = (() => {
    const raw = ledger.data?.statement;
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      return (raw as { outstanding?: string | number }).outstanding;
    }
    return kpis.totalReceivable;
  })();
  const itemWise = useMemo(
    () => (ledger.data?.itemWise as Record<string, unknown>[]) ?? [],
    [ledger.data],
  );

  const [profileForm, setProfileForm] = useState({
    name: '',
    phone: '',
    email: '',
    gstin: '',
    pan: '',
    billingAddress: '',
    creditLimit: '',
    creditDays: '',
    partyBankName: '',
    partyBankAccount: '',
    partyBankIfsc: '',
  });
  const [partyCustom, setPartyCustom] = useState<Record<string, string>>({});
  const [addresses, setAddresses] = useState<ShippingAddress[]>([]);
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany });

  useEffect(() => {
    if (!ledger.data) return;
    setProfileForm({
      name: String(profile.name ?? ''),
      phone: String(profile.phone ?? ''),
      email: String(profile.email ?? ''),
      gstin: String(profile.gstin ?? ''),
      pan: String(profile.pan ?? ''),
      billingAddress: String(profile.billingAddress ?? ''),
      creditLimit: String(profile.creditLimit ?? ''),
      creditDays: String(profile.creditDays ?? ''),
      partyBankName: String(profile.partyBankName ?? ''),
      partyBankAccount: String(profile.partyBankAccount ?? ''),
      partyBankIfsc: String(profile.partyBankIfsc ?? ''),
    });
    const rows = (profile.shippingAddresses as ShippingAddress[]) ?? [];
    setAddresses(rows.length ? rows.map((a) => ({ label: a.label, address: a.address, isDefault: a.isDefault })) : [{ label: 'Default', address: String(profile.shippingAddress ?? ''), isDefault: true }]);
    setPartyCustom((profile.customFields as Record<string, string> | undefined) ?? {});
  }, [ledger.data, profile]);

  const saveProfile = useMutation({
    mutationFn: () =>
      updateCustomer(customer!.id, {
        ...profileForm,
        creditDays: profileForm.creditDays === '' ? undefined : Number(profileForm.creditDays),
        customFields: partyCustom,
        shippingAddresses: addresses,
      }),
    onSuccess: () => {
      setSaveError(null);
      void qc.invalidateQueries({ queryKey: ['customer-ledger-tabs', customer?.id] });
    },
    onError: (err) => setSaveError(getErrorMessage(err)),
  });

  const handleWhatsAppShare = () => {
    if (!customer) return;
    let formattedPhone = (customer.phone ?? '').replace(/\D/g, '');
    if (formattedPhone.length === 10) formattedPhone = `91${formattedPhone}`;
    const text = encodeURIComponent(
      `Hello ${customer.name},\nYour account statement from our shop:\nTotal Outstanding Balance: ${formatMoney(statementOutstanding as string | number | undefined)}\nThank you for your business!`,
    );
    const url = formattedPhone ? `https://wa.me/${formattedPhone}?text=${text}` : `https://wa.me/?text=${text}`;
    openShareUrl(url);
  };

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.customerLedger')}</PageTitle>
      <Stack className="no-print" direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'stretch', md: 'center' }}>
        <Autocomplete
          options={customerSearch.options}
          getOptionLabel={(o) => `${o.name}${o.phone ? ` (${o.phone})` : ''}`}
          filterOptions={(opts) => opts}
          value={customer}
          onChange={(_, v) => setCustomer(v)}
          onInputChange={(_, v) => customerSearch.setQuery(v)}
          loading={customerSearch.isFetching}
          sx={{ minWidth: 280, flex: 1 }}
          renderInput={(params) => (
            <TextField {...params} label={t('billing.customer')} placeholder="Type to search name, phone, or GSTIN" />
          )}
        />
        {customer && ledger.data ? (
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" color="success" startIcon={<WhatsAppIcon />} onClick={handleWhatsAppShare}>
              {t('reports.shareOnWhatsapp')}
            </Button>
            <Button variant="outlined" startIcon={<PrintIcon />} onClick={() => window.print()}>
              {t('common.print')}
            </Button>
            <Button
              variant="outlined"
              onClick={() => {
                void downloadCustomerLedgerXlsx(customer.id, {
                  date_from: filters.dateFrom || undefined,
                  date_to: filters.dateTo || undefined,
                  txn_type: txnType || undefined,
                  status: txnStatus || undefined,
                })
                  .then((blob) => triggerBlobDownload(blob, `${customer.name || customer.id}-ledger.xlsx`))
                  .catch(() => {});
              }}
            >
              {t('ledger.downloadExcel')}
            </Button>
          </Stack>
        ) : null}
      </Stack>
      <HistoryFilterBar
        value={filters}
        onChange={setFilters}
        dateRangePresets
        searchPlaceholder={t('common.search')}
      />

      {!customer ? <EmptyState description="Select a customer to view ledger transactions and outstanding balance." /> : null}
      {customer && ledger.isLoading ? <LoadingState /> : null}
      {ledger.isError ? (
        <ErrorState message={getErrorMessage(ledger.error)} error={ledger.error} onRetry={() => void ledger.refetch()} />
      ) : null}
      {ledger.data ? (
        <>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            {[
              [t('reports.dueBalance'), kpis.totalReceivable],
              [t('ledger.overdue'), kpis.overdueAmount],
              [t('ledger.totalSales'), kpis.totalSalesAmount],
              [t('ledger.totalReceived'), kpis.totalReceivedAmount],
            ].map(([label, val]) => (
              <Paper key={String(label)} sx={{ p: 2, flex: 1 }}>
                <Typography variant="caption" color="text.secondary">{String(label)}</Typography>
                <Typography variant="h6">{formatMoney(toNumber(val as string | number))}</Typography>
              </Paper>
            ))}
          </Stack>
          <Tabs value={tab} onChange={(_, v) => setTab(v)}>
            <Tab label={t('ledger.transactions')} />
            <Tab label={t('ledger.profile')} />
            <Tab label={t('ledger.itemWise')} />
            <Tab label={t('ledger.statement')} />
          </Tabs>

          {tab === 0 ? (
            <Stack spacing={1}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <TextField select size="small" label={t('common.type')} value={txnType} onChange={(e) => setTxnType(e.target.value)} sx={{ maxWidth: 220 }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                <MenuItem value="SALES">{t('nav.sales')}</MenuItem>
                <MenuItem value="PAYMENT_IN">{t('nav.receipts')}</MenuItem>
                <MenuItem value="QUOTATION">{t('nav.quotations')}</MenuItem>
                <MenuItem value="SALES_RETURN">{t('nav.salesReturns')}</MenuItem>
                <MenuItem value="CREDIT_NOTE">{t('nav.creditNotes')}</MenuItem>
                <MenuItem value="DEBIT_NOTE">{t('nav.debitNotes')}</MenuItem>
              </TextField>
              <TextField select size="small" label={t('common.status')} value={txnStatus} onChange={(e) => setTxnStatus(e.target.value)} sx={{ maxWidth: 220 }}>
                <MenuItem value="">{t('common.all')}</MenuItem>
                <MenuItem value="PAID">{t('status.PAID')}</MenuItem>
                <MenuItem value="UNPAID">{t('status.UNPAID')}</MenuItem>
                <MenuItem value="PARTIAL">{t('status.PARTIAL')}</MenuItem>
                <MenuItem value="OVERDUE">{t('status.OVERDUE')}</MenuItem>
                <MenuItem value="CANCELLED">{t('status.CANCELLED')}</MenuItem>
              </TextField>
              </Stack>
              {transactions.length === 0 ? (
                <EmptyState description="No transactions found for the selected date range." />
              ) : (
                <Paper sx={{ overflow: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>{t('common.date')}</TableCell>
                        <TableCell>{t('common.type')}</TableCell>
                        <TableCell>{t('common.number')}</TableCell>
                        <TableCell align="right">{t('common.total')}</TableCell>
                        <TableCell>{t('common.status')}</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {transactions.map((row, idx) => (
                        <TableRow key={`${row.number}-${idx}`}>
                          <TableCell>{String(row.date ?? '')}</TableCell>
                          <TableCell>{String(row.txnType ?? '')}</TableCell>
                          <TableCell>
                            {row.sourcePath ? (
                              <Typography component={RouterLink} to={String(row.sourcePath)} sx={{ color: 'primary.main', textDecoration: 'none' }}>
                                {String(row.number ?? '—')}
                              </Typography>
                            ) : (
                              String(row.number ?? '—')
                            )}
                          </TableCell>
                          <TableCell align="right">{formatMoney(toNumber(row.amount as string | number))}</TableCell>
                          <TableCell>{String(row.paymentState ?? row.status ?? '')}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Paper>
              )}
            </Stack>
          ) : null}

          {tab === 1 ? (
            <Stack spacing={2}>
              {saveError ? <HelpErrorAlert message={saveError} /> : null}
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} flexWrap="wrap" useFlexGap>
                <TextField size="small" label={t('common.name')} value={profileForm.name} onChange={(e) => setProfileForm((f) => ({ ...f, name: e.target.value }))} />
                <TextField size="small" label={t('common.phone')} value={profileForm.phone} onChange={(e) => setProfileForm((f) => ({ ...f, phone: e.target.value }))} />
                <TextField size="small" label={t('common.email')} value={profileForm.email} onChange={(e) => setProfileForm((f) => ({ ...f, email: e.target.value }))} />
                <TextField size="small" label="GSTIN" value={profileForm.gstin} onChange={(e) => setProfileForm((f) => ({ ...f, gstin: e.target.value }))} />
                <TextField size="small" label="PAN" value={profileForm.pan} onChange={(e) => setProfileForm((f) => ({ ...f, pan: e.target.value }))} />
                <TextField size="small" label={t('ledger.creditLimit')} value={profileForm.creditLimit} onChange={(e) => setProfileForm((f) => ({ ...f, creditLimit: e.target.value }))} />
                <TextField size="small" label={t('ledger.creditDays')} value={profileForm.creditDays} onChange={(e) => setProfileForm((f) => ({ ...f, creditDays: e.target.value }))} />
              </Stack>
              <TextField size="small" multiline minRows={2} label={t('billing.billingAddress')} value={profileForm.billingAddress} onChange={(e) => setProfileForm((f) => ({ ...f, billingAddress: e.target.value }))} />
              <Typography variant="subtitle2">{t('ledger.partyBank')}</Typography>
              <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
                <TextField size="small" label={t('billing.bankName')} value={profileForm.partyBankName} onChange={(e) => setProfileForm((f) => ({ ...f, partyBankName: e.target.value }))} />
                <TextField size="small" label={t('setup.bankAccount')} value={profileForm.partyBankAccount} onChange={(e) => setProfileForm((f) => ({ ...f, partyBankAccount: e.target.value }))} />
                <TextField size="small" label="IFSC" value={profileForm.partyBankIfsc} onChange={(e) => setProfileForm((f) => ({ ...f, partyBankIfsc: e.target.value }))} />
              </Stack>
              <Typography variant="subtitle2">{t('ledger.shippingAddresses')}</Typography>
              {addresses.map((addr, idx) => (
                <Stack key={idx} direction={{ xs: 'column', md: 'row' }} spacing={1}>
                  <TextField size="small" label={t('common.name')} value={addr.label} onChange={(e) => setAddresses((prev) => prev.map((a, i) => (i === idx ? { ...a, label: e.target.value } : a)))} />
                  <TextField size="small" fullWidth label={t('billing.deliveryAddress')} value={addr.address} onChange={(e) => setAddresses((prev) => prev.map((a, i) => (i === idx ? { ...a, address: e.target.value } : a)))} />
                  <Button size="small" onClick={() => setAddresses((prev) => prev.filter((_, i) => i !== idx))}>{t('common.remove')}</Button>
                </Stack>
              ))}
              <Button size="small" onClick={() => setAddresses((prev) => [...prev, { label: '', address: '', isDefault: false }])}>
                {t('ledger.addShippingAddress')}
              </Button>
              {activeCustomFieldDefs(company.data?.partyCustomFieldDefs).map((def) => (
                <TextField
                  key={def.key}
                  size="small"
                  label={def.label}
                  value={partyCustom[def.key] ?? ''}
                  onChange={(e) => setPartyCustom((prev) => ({ ...prev, [def.key]: e.target.value }))}
                />
              ))}
              <Button variant="contained" disabled={!customer || saveProfile.isPending} onClick={() => saveProfile.mutate()}>
                {t('common.save')}
              </Button>
            </Stack>
          ) : null}

          {tab === 2 ? (
            itemWise.length === 0 ? (
              <EmptyState description={t('ledger.itemWiseEmpty')} />
            ) : (
              <Paper sx={{ overflow: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('common.product')}</TableCell>
                      <TableCell>{t('products.skuRequired')}</TableCell>
                      <TableCell align="right">{t('common.qty')}</TableCell>
                      <TableCell align="right">{t('common.total')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {itemWise.map((row) => (
                      <TableRow key={String(row.productId)}>
                        <TableCell>{String(row.productName ?? '')}</TableCell>
                        <TableCell>{String(row.sku ?? '')}</TableCell>
                        <TableCell align="right">{String(row.salesQty ?? '')}</TableCell>
                        <TableCell align="right">{formatMoney(toNumber(row.salesAmount as string | number))}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            )
          ) : null}

          {tab === 3 ? (
            statementEntries.length === 0 ? (
              <EmptyState description="No transactions found for the selected date range." />
            ) : (
              <Paper sx={{ overflow: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>{t('ledger.srNo')}</TableCell>
                      <TableCell>{t('common.date')}</TableCell>
                      <TableCell>{t('common.type')}</TableCell>
                      <TableCell>{t('common.number')}</TableCell>
                      <TableCell>{t('billing.paymentMode')}</TableCell>
                      <TableCell align="right">{t('reports.billedAmount')}</TableCell>
                      <TableCell align="right">{t('reports.receivedAmount')}</TableCell>
                      <TableCell align="right">{t('reports.dueBalance')}</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {statementEntries.map((e, idx) => (
                      <TableRow key={`${e.date}-${e.number}-${idx}`}>
                        <TableCell>{String(e.srNo ?? e.sr_no ?? idx + 1)}</TableCell>
                        <TableCell>{String(e.date ?? '')}</TableCell>
                        <TableCell>{String(e.type ?? '')}</TableCell>
                        <TableCell>{String(e.number ?? '—')}</TableCell>
                        <TableCell>{String(e.mode ?? e.paymentMode ?? '')}</TableCell>
                        <TableCell align="right">{formatMoney(toNumber(e.debit as string | number))}</TableCell>
                        <TableCell align="right">{formatMoney(toNumber(e.credit as string | number))}</TableCell>
                        <TableCell align="right">{formatMoney(toNumber(e.balance as string | number))}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            )
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
