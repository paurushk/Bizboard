import { useState } from 'react';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getErrorMessage } from '@/api/client';
import {
  advisorBook, chooseOption, createOptionSet, createPolicyProduct, createProspect, issuePolicy, listPolicyProducts,
} from '@/api/roadmap';
import { isInsuranceEnabled } from '@/config/features';
import { EmptyState, ErrorState, LoadingState } from '@/components/PageState';
import { PageTitle } from '@/contextHelp';
import { enumLabel } from '@/utils/enumLabels';
import { formatMoney } from '@/utils/money';
import { t } from '@/i18n';
import { CustomerField, localDateInput } from '@/pages/growth/widgets';
import { PageShell } from '@/pages/phase/phaseShared';
import type { Customer } from '@/types/domain';

function rowsOf(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const results = (data as { results?: Record<string, unknown>[] } | null)?.results;
  return results ?? [];
}

export function InsurancePage() {
  if (!isInsuranceEnabled()) {
    return <PageShell title={t('nav.insurance')}><Typography>{t('erp.moduleDisabled')}</Typography></PageShell>;
  }
  return <InsuranceInner />;
}

function InsuranceInner() {
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [insurer, setInsurer] = useState('');
  const [line, setLine] = useState('MOTOR');
  const [premium, setPremium] = useState('');
  const [sumInsured, setSumInsured] = useState('');
  const [tenureMonths, setTenureMonths] = useState('12');
  const [prospectName, setProspectName] = useState('');
  const [prospectId, setProspectId] = useState<number | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [optionSetId, setOptionSetId] = useState<number | null>(null);
  const [options, setOptions] = useState<{ id: number; product: number }[]>([]);
  const [chosen, setChosen] = useState<number | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [nominee, setNominee] = useState('');
  const [startDate, setStartDate] = useState(localDateInput());
  const [error, setError] = useState('');
  const products = useQuery({ queryKey: ['policy-products'], queryFn: listPolicyProducts });
  const book = useQuery({ queryKey: ['advisor-book'], queryFn: advisorBook });
  const productRows = rowsOf(products.data);
  const create = useMutation({
    mutationFn: () => createPolicyProduct({
      name,
      insurerName: insurer,
      line,
      tenureMonths: Number(tenureMonths),
      sumInsured,
      premium,
    }),
    onSuccess: () => {
      setName('');
      void qc.invalidateQueries({ queryKey: ['policy-products'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const saveProspect = useMutation({
    mutationFn: () => createProspect(prospectName),
    onSuccess: (row) => {
      setProspectId(row.id);
      setOptionSetId(null);
      setOptions([]);
      setChosen(null);
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const offer = useMutation({
    mutationFn: () => createOptionSet(prospectId!, picked),
    onSuccess: (row) => {
      setOptionSetId(row.id);
      setOptions((row.options ?? []).map((option) => ({ id: option.id, product: option.product })));
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const choose = useMutation({
    mutationFn: (optionId: number) => chooseOption(optionSetId!, optionId),
    onSuccess: (_row, optionId) => setChosen(optionId),
    onError: (err) => setError(getErrorMessage(err)),
  });
  const issue = useMutation({
    mutationFn: () => issuePolicy({
      option: chosen!, customer: customer!.id, nominee, startDate,
    }),
    onSuccess: () => {
      setChosen(null);
      void qc.invalidateQueries({ queryKey: ['advisor-book'] });
    },
    onError: (err) => setError(getErrorMessage(err)),
  });
  const productName = (id: number) => String(productRows.find((row) => Number(row.id) === id)?.name ?? id);

  return (
    <Stack spacing={2}>
      <PageTitle>{t('nav.insurance')}</PageTitle>
      <Typography variant="body2" color="text.secondary">{t('growth.insuranceDesk')}</Typography>
      {error ? <Typography color="error" role="alert">{error}</Typography> : null}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <TextField size="small" label={t('growth.product')} value={name} onChange={(e) => setName(e.target.value)} />
        <TextField size="small" label={t('growth.insurer')} value={insurer} onChange={(e) => setInsurer(e.target.value)} />
        <TextField select size="small" label={t('growth.line')} value={line} onChange={(e) => setLine(e.target.value)}>
          {['MOTOR', 'HEALTH', 'LIFE', 'OTHER'].map((value) => <MenuItem key={value} value={value}>{enumLabel('insuranceLine', value)}</MenuItem>)}
        </TextField>
        <TextField size="small" label={t('growth.premium')} value={premium} onChange={(e) => setPremium(e.target.value)} />
        <TextField size="small" label={t('growth.sumInsured')} value={sumInsured} onChange={(e) => setSumInsured(e.target.value)} />
        <TextField size="small" label={t('growth.tenureMonths')} value={tenureMonths} onChange={(e) => setTenureMonths(e.target.value)} />
        <Button variant="contained" disabled={!name.trim() || !insurer.trim() || !premium.trim() || !sumInsured.trim() || !/^\d+$/.test(tenureMonths) || create.isPending} onClick={() => create.mutate()}>{t('growth.create')}</Button>
      </Stack>
      {products.isLoading ? <LoadingState /> : null}
      {products.isError ? <ErrorState message={getErrorMessage(products.error)} error={products.error} onRetry={() => void products.refetch()} /> : null}
      {!products.isLoading && !products.isError && productRows.length === 0 ? (
        <EmptyState description={t('cog.emptyInsurance')} />
      ) : null}
      {productRows.map((row) => (
        <Stack key={String(row.id)} direction="row" spacing={1} alignItems="center">
          <input
            type="checkbox"
            aria-label={String(row.name)}
            checked={picked.includes(Number(row.id))}
            onChange={(e) => {
              const id = Number(row.id);
              setPicked((current) => (e.target.checked ? [...current, id] : current.filter((item) => item !== id)));
            }}
          />
          <Typography>{String(row.insurerName)} · {String(row.name)} · {formatMoney(row.premium as string | number)}</Typography>
        </Stack>
      ))}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <TextField size="small" label={t('growth.prospect')} value={prospectName} onChange={(e) => setProspectName(e.target.value)} />
        <Button variant="outlined" disabled={!prospectName.trim() || saveProspect.isPending} onClick={() => saveProspect.mutate()}>{t('growth.saveProspect')}</Button>
        <Button variant="outlined" disabled={prospectId == null || picked.length < 2 || offer.isPending} onClick={() => offer.mutate()}>{t('growth.offerOptions')}</Button>
      </Stack>
      {options.map((option) => (
        <Button key={option.id} size="small" variant={chosen === option.id ? 'contained' : 'text'} onClick={() => choose.mutate(option.id)}>
          {chosen === option.id ? t('growth.chosen') : t('growth.choose')} {productName(option.product)}
        </Button>
      ))}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1}>
        <CustomerField value={customer} onChange={setCustomer} />
        <TextField size="small" label={t('growth.nominee')} value={nominee} onChange={(e) => setNominee(e.target.value)} />
        <TextField size="small" type="date" label={t('growth.start')} InputLabelProps={{ shrink: true }} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        <Button variant="contained" disabled={chosen == null || !customer || issue.isPending} onClick={() => issue.mutate()}>{t('growth.issuePolicy')}</Button>
      </Stack>
      {book.isError ? <ErrorState message={getErrorMessage(book.error)} error={book.error} onRetry={() => void book.refetch()} /> : null}
      <Typography variant="subtitle2">{t('growth.inForce')}</Typography>
      {!book.isLoading && !book.isError && (book.data?.policies ?? []).length === 0 ? (
        <EmptyState description={t('cog.emptyInsurance')} />
      ) : null}
      {(book.data?.policies ?? []).map((row) => {
        const policy = row as Record<string, unknown>;
        return (
          <Typography key={String(policy.id)}>
            {String(policy.number)} · {String(policy.status)}
            {policy.endDate ? ` · ${t('growth.endsOn', { date: String(policy.endDate) })}` : ''}
          </Typography>
        );
      })}
    </Stack>
  );
}
