import { useState } from 'react';
import Alert from '@mui/material/Alert';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getNumberSeries, saveNumberSeries, type NumberSeriesList, type NumberSeriesRow } from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { AsyncSection } from '@/components/settings/AsyncSection';
import { SettingsPage } from '@/components/settings/SettingsPage';
import { SettingsSaveBar } from '@/components/settings/SettingsSaveBar';
import { useSettingsForm } from '@/hooks/useSettingsForm';
import { useSubscriptionGate } from '@/hooks/useSubscriptionGate';
import { t } from '@/i18n';
import { ForbiddenPage } from '@/pages/ForbiddenPage';
import { confirmAction } from '@/utils/confirmBridge';
import { confirmWithPreview } from '@/utils/settingsPreview';
import { settingsErrorText } from '@/utils/settingsErrors';

const NAME_KEYS: Record<string, string> = {
  SALES_INVOICE: 'cog.seriesSales',
  QUOTATION: 'cog.seriesQuotes',
  SALES_ORDER: 'cog.seriesOrders',
  DELIVERY_CHALLAN: 'cog.seriesChallans',
  SALES_CREDIT_NOTE: 'cog.seriesCredit',
  SALES_DEBIT_NOTE: 'cog.seriesDebit',
  PURCHASE_INVOICE: 'cog.seriesPurchases',
  PURCHASE_ORDER: 'cog.seriesPo',
  GOODS_RECEIPT: 'cog.seriesGrn',
  PURCHASE_CREDIT_NOTE: 'cog.seriesPcn',
  PURCHASE_DEBIT_NOTE: 'cog.seriesPdn',
};

/** Documents GST rules require to carry a serial number of at most 16 characters (warned, never blocked). */
const GST_LENGTH_TYPES = ['SALES_INVOICE', 'SALES_CREDIT_NOTE', 'SALES_DEBIT_NOTE'];
const GST_LENGTH_LIMIT = 16;

interface Selection {
  gstin: string;
  fy: string;
}

/**
 * SET-02: every document number series on one screen, for one GSTIN and financial year, saved
 * together (all or nothing) with a lock against another owner's edit. A series that cannot be
 * loaded never appears as an editable row: the whole list shows an error with Retry instead.
 */
export function SeriesSettingsPage() {
  const { user } = useAuth();
  const [selection, setSelection] = useState<Selection>({ gstin: '', fy: '' });
  const query = useQuery({
    queryKey: ['number-series', selection.gstin, selection.fy],
    queryFn: () => getNumberSeries(selection.gstin, selection.fy),
    enabled: user?.role === 'OWNER',
    refetchOnWindowFocus: false,
  });
  if (user?.role !== 'OWNER') return <ForbiddenPage />;
  return (
    <SettingsPage
      title={t('sweep2.docNumberSeries')}
      purpose={t('seriesPage.purpose')}
    >
      <Typography variant="caption" color="text.secondary">
        {t('phase1.quotationNumberGapNote')}
      </Typography>
      <AsyncSection query={query}>
        {(data) => (
          <Editor
            key={`${data.gstin}|${data.fyLabel}|${data.items.map((r) => r.updatedAt).join(',')}`}
            data={data}
            selection={selection}
            onSelect={setSelection}
          />
        )}
      </AsyncSection>
    </SettingsPage>
  );
}

type RowValues = Pick<NumberSeriesRow, 'docType' | 'prefix' | 'nextNumber' | 'padding' | 'updatedAt'>;

function sample(prefix: string, next: number, padding: number): string {
  const numStr = String(Math.max(1, next)).padStart(padding, '0');
  return prefix ? `${prefix}-${numStr}` : numStr;
}

function Editor({
  data,
  selection,
  onSelect,
}: {
  data: NumberSeriesList;
  selection: Selection;
  onSelect: (next: Selection) => void;
}) {
  const { writesBlocked } = useSubscriptionGate();
  const qc = useQueryClient();
  const initial: { rows: RowValues[] } = {
    rows: data.items.map((r) => ({
      docType: r.docType,
      prefix: r.prefix,
      nextNumber: r.nextNumber,
      padding: r.padding,
      updatedAt: r.updatedAt,
    })),
  };
  const form = useSettingsForm<{ rows: RowValues[] }, { updatedAt?: string | null }>({
    initial,
    // A non-null marker means "send each row's own timestamp"; Overwrite clears it.
    initialUpdatedAt: 'rows',
    save: async (values, ctx) => {
      const changed = values.rows.filter((row, i) => {
        const was = initial.rows[i];
        return row.prefix !== was.prefix || row.nextNumber !== was.nextNumber || row.padding !== was.padding;
      });
      if (changed.length === 0) return {};
      // A dry run first: the next five numbers each changed series would give, and the highest in use.
      const agreed = await confirmWithPreview(
        'series',
        {
          items: changed.map((row) => ({
            doc_type: row.docType,
            prefix: row.prefix,
            next_number: row.nextNumber,
            padding: row.padding,
          })),
        },
        t('settingsPreview.series_confirm'),
      );
      if (!agreed) throw new Error(t('gstPage.cancelled'));
      await saveNumberSeries(
        {
          gstin: data.gstin,
          fy: data.fyLabel,
          items: changed.map((row) => ({
            doc_type: row.docType,
            prefix: row.prefix,
            next_number: row.nextNumber,
            padding: row.padding,
            ...(ctx.expectedUpdatedAt ? { expected_updated_at: row.updatedAt } : {}),
          })),
        },
        ctx.headers,
      );
      await qc.invalidateQueries({ queryKey: ['number-series'] });
      return {};
    },
    refetch: async () => {
      const latest = await getNumberSeries(selection.gstin, selection.fy);
      await qc.invalidateQueries({ queryKey: ['number-series'] });
      return {
        values: {
          rows: latest.items.map((r) => ({
            docType: r.docType,
            prefix: r.prefix,
            nextNumber: r.nextNumber,
            padding: r.padding,
            updatedAt: r.updatedAt,
          })),
        },
        updatedAt: 'rows',
      };
    },
  });

  const setRow = (index: number, patch: Partial<RowValues>) =>
    form.setValues({ rows: form.values.rows.map((row, i) => (i === index ? { ...row, ...patch } : row)) });

  const choose = async (next: Selection) => {
    if (form.dirty && !(await confirmAction(t('seriesPage.leaveSelection')))) return;
    onSelect(next);
  };

  return (
    <>
      {form.error ? <Alert severity="error">{settingsErrorText(form.error)}</Alert> : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
        {data.gstins.length > 1 ? (
          <TextField
            select
            size="small"
            label={t('seriesPage.gstin')}
            value={data.gstin}
            onChange={(e) => void choose({ gstin: e.target.value, fy: selection.fy })}
            sx={{ minWidth: 220 }}
          >
            {data.gstins.map((g) => (
              <MenuItem key={g} value={g}>
                {g}
              </MenuItem>
            ))}
          </TextField>
        ) : null}
        <TextField
          select
          size="small"
          label={t('seriesPage.financialYear')}
          value={data.fyLabel || ''}
          onChange={(e) => void choose({ gstin: selection.gstin, fy: e.target.value })}
          helperText={t('seriesPage.fyHelp')}
          sx={{ minWidth: 180 }}
        >
          {data.fyOptions.map((fy) => (
            <MenuItem key={fy} value={fy}>
              {fy}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('sweep2.docType')}</TableCell>
              <TableCell>{t('sweep.prefix')}</TableCell>
              <TableCell align="right">{t('sweep2.nextNumber')}</TableCell>
              <TableCell align="right">{t('sweep2.padding')}</TableCell>
              <TableCell>{t('sweep2.nextSamplePreview')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {form.values.rows.map((row, i) => {
              const preview = sample(row.prefix, row.nextNumber, row.padding);
              const tooLong = GST_LENGTH_TYPES.includes(row.docType) && preview.length > GST_LENGTH_LIMIT;
              return (
                <TableRow key={row.docType}>
                  <TableCell sx={{ fontWeight: 500 }}>{t(NAME_KEYS[row.docType] ?? row.docType)}</TableCell>
                  <TableCell>
                    <TextField
                      size="small"
                      value={row.prefix}
                      onChange={(e) => setRow(i, { prefix: e.target.value })}
                      slotProps={{ htmlInput: { 'aria-label': `${t(NAME_KEYS[row.docType] ?? row.docType)} ${t('sweep.prefix')}`, maxLength: 16 } }}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <TextField
                      size="small"
                      type="number"
                      value={row.nextNumber}
                      onChange={(e) => setRow(i, { nextNumber: Math.max(1, parseInt(e.target.value, 10) || 1) })}
                      slotProps={{ htmlInput: { 'aria-label': `${t(NAME_KEYS[row.docType] ?? row.docType)} ${t('sweep2.nextNumber')}`, min: 1 } }}
                      sx={{ width: 110 }}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <TextField
                      size="small"
                      type="number"
                      value={row.padding}
                      onChange={(e) => setRow(i, { padding: Math.max(1, Math.min(10, parseInt(e.target.value, 10) || 1)) })}
                      slotProps={{ htmlInput: { 'aria-label': `${t(NAME_KEYS[row.docType] ?? row.docType)} ${t('sweep2.padding')}`, min: 1, max: 10 } }}
                      sx={{ width: 80 }}
                    />
                  </TableCell>
                  <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                    {preview}
                    {tooLong ? (
                      <Typography variant="caption" color="warning.main" display="block" role="note">
                        {t('seriesPage.tooLong', { count: preview.length })}
                      </Typography>
                    ) : null}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      <SettingsSaveBar form={form} disabled={writesBlocked} />
    </>
  );
}
