import { useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getTdsClaims, listPlatformInvoices, refundTdsClaim, submitTdsClaim } from '@/api/billing';
import { openAuthenticatedFile, uploadFile } from '@/api/resources';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';

/**
 * WP-BL2 / WP-BL1: Bizboard's GST invoices to this company (for input tax credit), and the claim
 * for TDS the company deducted on them. The TDS amount is worked out by the server from the
 * invoices' taxable value; the owner only picks the invoices, the section and the Form 16A.
 */
export function BizboardInvoicesPanel({ companyKey }: { companyKey: unknown }) {
  const qc = useQueryClient();
  const invoices = useQuery({ queryKey: ['platform-invoices', companyKey], queryFn: listPlatformInvoices });
  const claims = useQuery({ queryKey: ['tds-claims', companyKey], queryFn: getTdsClaims });
  const [picked, setPicked] = useState<number[]>([]);
  const [section, setSection] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [settleBy, setSettleBy] = useState<'CREDIT' | 'REFUND'>('CREDIT');
  const submit = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error(t('saasBilling.needCertificate'));
      const uploaded = await uploadFile(file, 'ATTACHMENT');
      return submitTdsClaim({ invoiceIds: picked, section, certificateId: uploaded.id, settleBy });
    },
    onSuccess: () => {
      setPicked([]);
      setFile(null);
      void qc.invalidateQueries({ queryKey: ['tds-claims'] });
    },
  });
  const refund = useMutation({
    mutationFn: refundTdsClaim,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['tds-claims'] }),
  });
  const pdf = useMutation({ mutationFn: (id: number) => openAuthenticatedFile(`/billing/invoices/${id}/pdf/`) });

  const rows = (invoices.data ?? []).filter((row) => row.kind === 'INVOICE');
  const sections = claims.data?.sections ?? [];
  const toggle = (id: number) => setPicked((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <Paper sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        <Typography variant="h6">{t('saasBilling.title')}</Typography>
        <Typography variant="body2" color="text.secondary">
          {t('saasBilling.help')}
        </Typography>
        {invoices.isError ? <HelpErrorAlert error={invoices.error} /> : null}
        {pdf.isError ? <HelpErrorAlert error={pdf.error} /> : null}
        {rows.length === 0 && invoices.isSuccess ? (
          <Typography color="text.secondary">{t('saasBilling.none')}</Typography>
        ) : null}
        {(invoices.data ?? []).map((row) => (
          <Stack key={row.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body2">
              {t(row.kind === 'INVOICE' ? 'saasBilling.invoiceLine' : 'saasBilling.creditLine', {
                number: row.number,
                date: String(row.createdAt).slice(0, 10),
                total: formatMoney(Number(row.total)),
                gstin: row.buyerGstin || t('saasBilling.noGstin'),
              })}
            </Typography>
            <Button
              size="small"
              aria-label={t('saasBilling.pdfFor', { number: row.number })}
              disabled={pdf.isPending}
              onClick={() => pdf.mutate(row.id)}
            >
              {t('saasBilling.pdf')}
            </Button>
          </Stack>
        ))}

        {rows.length > 0 ? (
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography fontWeight={600}>{t('saasBilling.tdsTitle')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('saasBilling.tdsHelp')}
            </Typography>
            {rows.map((row) => (
              <FormControlLabel
                key={row.id}
                control={<Checkbox checked={picked.includes(row.id)} onChange={() => toggle(row.id)} />}
                label={`${row.number} · ${formatMoney(Number(row.taxableAmount))}`}
              />
            ))}
            <TextField
              select
              label={t('saasBilling.section')}
              value={section}
              onChange={(e) => setSection(e.target.value)}
              sx={{ maxWidth: 360 }}
            >
              {sections.map((s) => (
                <MenuItem key={s.code} value={s.code}>
                  {s.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label={t('saasBilling.settleBy')}
              value={settleBy}
              onChange={(e) => setSettleBy(e.target.value === 'REFUND' ? 'REFUND' : 'CREDIT')}
              sx={{ maxWidth: 360 }}
            >
              <MenuItem value="CREDIT">{t('saasBilling.settleCredit')}</MenuItem>
              <MenuItem value="REFUND">{t('saasBilling.settleRefund')}</MenuItem>
            </TextField>
            <Button variant="outlined" component="label" sx={{ alignSelf: 'flex-start' }}>
              {file ? file.name : t('saasBilling.attach16a')}
              <input hidden type="file" accept="application/pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Button>
            {submit.isError ? <HelpErrorAlert error={submit.error} /> : null}
            {submit.isSuccess ? <Alert severity="success">{t('saasBilling.claimSent')}</Alert> : null}
            <Button
              variant="contained"
              sx={{ alignSelf: 'flex-start' }}
              disabled={!picked.length || !section || !file || submit.isPending}
              onClick={() => submit.mutate()}
            >
              {t('saasBilling.submitClaim')}
            </Button>
          </Stack>
        ) : null}

        {refund.isError ? <HelpErrorAlert error={refund.error} /> : null}
        {(claims.data?.claims ?? []).map((claim) => {
          const creditLeft = Number(claim.creditRemaining || 0);
          const canRefund =
            claim.settleBy === 'CREDIT' && (claim.status === 'SUBMITTED' || (claim.status === 'VERIFIED' && creditLeft > 0));
          return (
            <Stack key={claim.id} direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="body2">
                {t('saasBilling.claimLine', {
                  quarter: claim.quarter,
                  amount: formatMoney(Number(claim.amount)),
                  status: t(`saasBilling.status.${claim.status}`),
                })}
                {claim.status === 'REJECTED' && claim.reviewNote ? ` — ${claim.reviewNote}` : ''}
                {claim.status === 'VERIFIED' && creditLeft > 0
                  ? ` · ${t('saasBilling.creditLeft', { amount: formatMoney(creditLeft) })}`
                  : ''}
              </Typography>
              {canRefund ? (
                <Button size="small" disabled={refund.isPending} onClick={() => refund.mutate(claim.id)}>
                  {t('saasBilling.refundInstead')}
                </Button>
              ) : null}
            </Stack>
          );
        })}
      </Stack>
    </Paper>
  );
}
