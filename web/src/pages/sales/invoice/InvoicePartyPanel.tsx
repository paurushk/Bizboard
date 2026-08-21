import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createCustomer, listCustomersPage, updateCustomer } from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { PartySelectPanel } from '@/components/PartySelectPanel';
import { StateSelect } from '@/components/StateSelect';
import { t } from '@/i18n';
import type { Customer, SalesInvoice } from '@/types/domain';
import { isValidGstin } from '@/utils/gst';
import { placeOfSupplyKnown } from '@/utils/tax';

type Props = {
  selectedCustomer: Customer | undefined;
  editingStatus: SalesInvoice['status'] | null;
  options: Customer[];
  query: string;
  onQueryChange: (q: string) => void;
  onSelect: (c: Customer | null | undefined) => void;
  loading: boolean;
  /** When true, show inline state/GSTIN editor if place of supply is unknown. */
  requirePlaceOfSupply?: boolean;
  onCustomerCreated: (c: Customer) => void;
  onCustomerUpdated?: (c: Customer) => void;
  onError: (msg: string) => void;
};

/**
 * BB-000751: bill-to party select + create-party dialog for NewInvoicePage.
 */
export function InvoicePartyPanel({
  selectedCustomer,
  editingStatus,
  options,
  query,
  onQueryChange,
  onSelect,
  loading,
  requirePlaceOfSupply = false,
  onCustomerCreated,
  onCustomerUpdated,
  onError,
}: Props) {
  const qc = useQueryClient();
  const [partyDialogOpen, setPartyDialogOpen] = useState(false);
  const [partyForm, setPartyForm] = useState({ name: '', phone: '', gstin: '', state: '' });
  const [posForm, setPosForm] = useState({ state: '', gstin: '' });

  const needsPosEditor =
    Boolean(requirePlaceOfSupply) &&
    Boolean(selectedCustomer) &&
    editingStatus !== 'COMPLETED' &&
    !placeOfSupplyKnown(selectedCustomer?.state, selectedCustomer?.gstin);

  useEffect(() => {
    setPosForm({
      state: selectedCustomer?.state ?? '',
      gstin: selectedCustomer?.gstin ?? '',
    });
  }, [selectedCustomer?.id, selectedCustomer?.state, selectedCustomer?.gstin]);

  const partyMutation = useMutation({
    mutationFn: async () => {
      const gstin = partyForm.gstin.trim().toUpperCase();
      if (gstin) {
        if (!isValidGstin(gstin)) throw new Error('Enter a valid 15-character GSTIN.');
        const existing = await listCustomersPage({ gstin, pageSize: 5 });
        if (existing.results.some((c) => (c.gstin ?? '').toUpperCase() === gstin)) {
          throw new Error('A customer with this GSTIN already exists.');
        }
      }
      return createCustomer({
        name: partyForm.name.trim(),
        phone: partyForm.phone,
        gstin: gstin || partyForm.gstin,
        state: partyForm.state,
        status: 'ACTIVE',
      });
    },
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ['customers-search'] });
      void qc.invalidateQueries({ queryKey: ['customer'] });
      setPartyDialogOpen(false);
      setPartyForm({ name: '', phone: '', gstin: '', state: '' });
      onCustomerCreated(c);
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  const posMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCustomer) throw new Error('Customer is required');
      const gstin = posForm.gstin.trim().toUpperCase();
      if (gstin && !isValidGstin(gstin)) {
        throw new Error('Enter a valid 15-character GSTIN.');
      }
      if (!placeOfSupplyKnown(posForm.state, gstin)) {
        throw new Error(t('billing.placeOfSupplyRequired'));
      }
      if (gstin) {
        const existing = await listCustomersPage({ gstin, pageSize: 5 });
        if (
          existing.results.some(
            (c) => c.id !== selectedCustomer.id && (c.gstin ?? '').toUpperCase() === gstin,
          )
        ) {
          throw new Error('A customer with this GSTIN already exists.');
        }
      }
      return updateCustomer(selectedCustomer.id, {
        state: posForm.state,
        gstin: gstin || '',
      });
    },
    onSuccess: (c) => {
      void qc.invalidateQueries({ queryKey: ['customers-search'] });
      void qc.invalidateQueries({ queryKey: ['customer', c.id] });
      onCustomerUpdated?.(c);
    },
    onError: (err) => onError(getErrorMessage(err)),
  });

  const handleQuickWalkIn = async () => {
    const existing = options.find((c) => /walk[\s-]?in|cash/i.test(c.name));
    if (existing) {
      onSelect(existing);
      return;
    }
    try {
      const searchRes = await listCustomersPage({ q: 'Walk-in', pageSize: 5 });
      const found = searchRes.results.find((c) => /walk[\s-]?in|cash/i.test(c.name));
      if (found) {
        onSelect(found);
        return;
      }
      const created = await createCustomer({
        name: 'Walk-in Customer',
        status: 'ACTIVE',
      });
      void qc.invalidateQueries({ queryKey: ['customers-search'] });
      onCustomerCreated(created);
      onSelect(created);
    } catch {
      setPartyDialogOpen(true);
      setPartyForm({ name: 'Walk-in Customer', phone: '', gstin: '', state: '' });
    }
  };

  return (
    <>
      <Stack spacing={1} sx={{ flex: 1.2, minWidth: 0 }}>
        <PartySelectPanel
          label={t('billing.billTo')}
          selectedParty={selectedCustomer}
          editingStatus={editingStatus}
          onClear={() => onSelect(undefined)}
          options={options}
          query={query}
          onQueryChange={onQueryChange}
          onSelect={(v) => onSelect(v)}
          loading={loading}
          onCreatePartyClick={() => setPartyDialogOpen(true)}
          onQuickCashClick={handleQuickWalkIn}
          sx={{ flex: 'none', width: '100%' }}
        />

        {needsPosEditor ? (
          <Stack
            spacing={1.5}
            sx={{
              border: '1px dashed',
              borderColor: 'warning.main',
              borderRadius: 1,
              p: 1.5,
            }}
          >
            <Alert severity="warning" sx={{ py: 0 }}>
              {t('billing.placeOfSupplyRequired')}
            </Alert>
            <StateSelect
              value={posForm.state}
              onChange={(state) => setPosForm((f) => ({ ...f, state }))}
            />
            <TextField
              label="GSTIN"
              value={posForm.gstin}
              onChange={(e) => setPosForm((f) => ({ ...f, gstin: e.target.value }))}
              fullWidth
            />
            <Button
              variant="contained"
              size="small"
              disabled={
                posMutation.isPending || !placeOfSupplyKnown(posForm.state, posForm.gstin)
              }
              onClick={() => posMutation.mutate()}
            >
              {t('common.save')}
            </Button>
          </Stack>
        ) : null}
      </Stack>

      <Dialog
        open={partyDialogOpen}
        onClose={() => setPartyDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('billing.createParty')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              required
              label={t('common.name')}
              value={partyForm.name}
              onChange={(e) => setPartyForm((f) => ({ ...f, name: e.target.value }))}
            />
            <TextField
              label={t('common.phone')}
              value={partyForm.phone}
              onChange={(e) => setPartyForm((f) => ({ ...f, phone: e.target.value }))}
            />
            <TextField
              label="GSTIN"
              value={partyForm.gstin}
              onChange={(e) => setPartyForm((f) => ({ ...f, gstin: e.target.value }))}
            />
            <StateSelect
              value={partyForm.state}
              onChange={(state) => setPartyForm((f) => ({ ...f, state }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPartyDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!partyForm.name.trim() || partyMutation.isPending}
            onClick={() => partyMutation.mutate()}
          >
            {t('common.create')}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
