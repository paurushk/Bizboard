import { useEffect, useMemo, useState } from 'react';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import Tab from '@mui/material/Tab';
import Tabs from '@mui/material/Tabs';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { getCompany, getSalesInvoiceNumberSeries, updateCompany } from '@/api/resources';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import {
  normalizeCustomFieldDefs,
  suggestCustomFieldKey,
  type ItemCustomFieldDef,
} from '@/pages/inventory/itemCustomFieldDefaults';

const INDUSTRY_PRESETS: Record<string, Array<{ key: string; label: string }>> = {
  trading: [
    { key: 'po_number', label: 'PO Number' },
    { key: 'eway_bill_number', label: 'E-way Bill Number' },
    { key: 'vehicle_number', label: 'Vehicle Number' },
  ],
  manufacturing: [
    { key: 'job_card', label: 'Job card' },
    { key: 'batch_ref', label: 'Batch reference' },
  ],
  services: [{ key: 'work_order', label: 'Work order' }],
};

const INDUSTRY_STORAGE_KEY = 'bizboard:invoice-industry-preset';
export const SHOW_PURCHASE_PRICE_KEY = 'bizboard:show-purchase-price';

type Props = {
  open: boolean;
  onClose: () => void;
  showBatchCols: boolean;
  onShowBatchColsChange: (next: boolean) => void;
  showPurchasePrice: boolean;
  onShowPurchasePriceChange: (next: boolean) => void;
};

function DefEditor({
  defs,
  onChange,
}: {
  defs: ItemCustomFieldDef[];
  onChange: (next: ItemCustomFieldDef[]) => void;
}) {
  const [label, setLabel] = useState('');
  return (
    <Stack spacing={1}>
      {defs.filter((d) => d.active !== false).map((def) => (
        <Stack key={def.key} direction="row" spacing={1} alignItems="center">
          <TextField size="small" label={t('customFields.key')} value={def.key} disabled sx={{ width: 140 }} />
          <TextField size="small" label={t('customFields.label')} value={def.label} disabled sx={{ flex: 1 }} />
          <Button
            size="small"
            color="inherit"
            onClick={() => onChange(defs.map((row) => (row.key === def.key ? { ...row, active: false } : row)))}
          >
            {t('common.remove')}
          </Button>
        </Stack>
      ))}
      <Stack direction="row" spacing={1}>
        <TextField
          size="small"
          label={t('customFields.label')}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Button
          size="small"
          variant="outlined"
          disabled={!label.trim()}
          onClick={() => {
            let key = suggestCustomFieldKey(label);
            if (!key) return;
            const used = new Set(defs.map((d) => d.key.toLowerCase()));
            let n = 2;
            let unique = key;
            while (used.has(unique.toLowerCase())) {
              unique = `${key}${n}`;
              n += 1;
            }
            onChange([...defs, { key: unique, label: label.trim(), type: 'text', active: true }]);
            setLabel('');
          }}
        >
          {t('common.add')}
        </Button>
      </Stack>
    </Stack>
  );
}

export function InvoiceQuickSettingsDialog({
  open,
  onClose,
  showBatchCols,
  onShowBatchColsChange,
  showPurchasePrice,
  onShowPurchasePriceChange,
}: Props) {
  const qc = useQueryClient();
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany, enabled: open });
  const series = useQuery({
    queryKey: ['sales-invoice-number-series'],
    queryFn: getSalesInvoiceNumberSeries,
    enabled: open,
  });
  const [tab, setTab] = useState(0);
  const [industry, setIndustry] = useState(() => {
    try {
      return localStorage.getItem(INDUSTRY_STORAGE_KEY) || 'trading';
    } catch {
      return 'trading';
    }
  });
  const [invoiceDefs, setInvoiceDefs] = useState<ItemCustomFieldDef[]>([]);
  const [partyDefs, setPartyDefs] = useState<ItemCustomFieldDef[]>([]);
  const [showEmptySignatureBox, setShowEmptySignatureBox] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!company.data || !open) return;
    setInvoiceDefs(normalizeCustomFieldDefs(company.data.invoiceCustomFieldDefs ?? []));
    setPartyDefs(normalizeCustomFieldDefs(company.data.partyCustomFieldDefs ?? []));
    setShowEmptySignatureBox(Boolean(company.data.showEmptySignatureBox));
  }, [company.data, open]);

  const save = useMutation({
    mutationFn: () =>
      updateCompany({
        invoiceCustomFieldDefs: invoiceDefs,
        partyCustomFieldDefs: partyDefs,
        showEmptySignatureBox,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['company'] });
      onClose();
    },
    onError: (err) => setError(getErrorMessage(err)),
  });

  const applyPreset = (preset: string) => {
    setIndustry(preset);
    try {
      localStorage.setItem(INDUSTRY_STORAGE_KEY, preset);
    } catch {
      // ignore
    }
    const extra = INDUSTRY_PRESETS[preset] ?? [];
    setInvoiceDefs((prev) => {
      const keys = new Set(prev.map((d) => d.key));
      const added = extra
        .filter((row) => !keys.has(row.key))
        .map((row) => ({ ...row, type: 'text' as const, active: true }));
      return [...prev, ...added];
    });
  };

  const invoiceActive = useMemo(() => invoiceDefs.filter((d) => d.active !== false), [invoiceDefs]);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{t('billing.quickSettings')}</DialogTitle>
      <DialogContent>
        <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
          <Tab label={t('billing.invoiceDetailsTab')} />
          <Tab label={t('billing.partyDetailsTab')} />
          <Tab label={t('billing.itemTableTab')} />
        </Tabs>
        {error ? <HelpErrorAlert message={error} /> : null}
        {tab === 0 ? (
          <Stack spacing={2}>
            <TextField
              select
              size="small"
              label={t('billing.industryType')}
              value={industry}
              onChange={(e) => applyPreset(e.target.value)}
              helperText={t('billing.industryTypeHelp')}
            >
              <MenuItem value="trading">{t('billing.industryTrading')}</MenuItem>
              <MenuItem value="manufacturing">{t('billing.industryManufacturing')}</MenuItem>
              <MenuItem value="services">{t('billing.industryServices')}</MenuItem>
            </TextField>
            <Typography variant="body2">
              {t('billing.numberPreview')}: {series.data?.preview ?? '—'}
            </Typography>
            <Button component={RouterLink} to="/settings/series" onClick={onClose} size="small">
              {t('nav.seriesSettings')}
            </Button>
            <Button component={RouterLink} to="/settings/templates" onClick={onClose} size="small">
              {t('nav.invoiceTemplates')}
            </Button>
            <Typography variant="subtitle2">{t('billing.invoiceCustomFields')}</Typography>
            <DefEditor defs={invoiceDefs} onChange={setInvoiceDefs} />
            <FormControlLabel
              control={
                <Checkbox
                  checked={showEmptySignatureBox}
                  onChange={(e) => setShowEmptySignatureBox(e.target.checked)}
                />
              }
              label={t('billing.emptySignatureBox')}
            />
            {invoiceActive.length ? (
              <Typography variant="caption" color="text.secondary">
                {invoiceActive.map((d) => d.label).join(' · ')}
              </Typography>
            ) : null}
          </Stack>
        ) : null}
        {tab === 1 ? (
          <Stack spacing={2}>
            <Typography variant="subtitle2">{t('billing.partyCustomFields')}</Typography>
            <DefEditor defs={partyDefs} onChange={setPartyDefs} />
          </Stack>
        ) : null}
        {tab === 2 ? (
          <Stack spacing={1}>
            <FormControlLabel
              control={<Checkbox checked={showBatchCols} onChange={(e) => onShowBatchColsChange(e.target.checked)} />}
              label={t('billing.showBatchColumns')}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={showPurchasePrice}
                  onChange={(e) => onShowPurchasePriceChange(e.target.checked)}
                />
              }
              label={t('billing.showPurchasePrice')}
            />
            <Button component={RouterLink} to="/settings/items" onClick={onClose}>
              {t('billing.itemCustomFieldsLink')}
            </Button>
            <Button component={RouterLink} to="/settings/templates" onClick={onClose}>
              {t('nav.invoiceTemplates')}
            </Button>
          </Stack>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
        <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()}>
          {t('common.save')}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
