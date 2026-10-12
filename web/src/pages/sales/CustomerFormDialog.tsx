import { useEffect, useMemo, useRef, useState } from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import FormControlLabel from '@mui/material/FormControlLabel';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery } from '@tanstack/react-query';
import { getErrorDetails, getErrorMessage } from '@/api/client';
import {
  createCustomer,
  getCompany,
  getCustomer,
  listPriceLists,
  lookupCustomerGstin,
  updateCustomer,
} from '@/api/resources';
import { useAuth } from '@/auth/AuthContext';
import { StateSelect } from '@/components/StateSelect';
import { t } from '@/i18n';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';
import { activeCustomFieldDefs } from '@/pages/inventory/itemCustomFieldDefaults';
import type { Customer, GstinLookup, ShippingAddress, TaxpayerType } from '@/types/domain';
import { isValidGstin, isValidIndianPhone } from '@/utils/gst';
import { getStateFromGstin } from '@/utils/indianStates';
import { partyNameError } from '@/utils/partyName';
import { isValidIndianPincode } from '@/utils/pincode';
import { placeOfSupplyKnown } from '@/utils/tax';

const TAXPAYER_TYPES: TaxpayerType[] = [
  'REGULAR', 'COMPOSITION', 'UNREGISTERED', 'SEZWP', 'SEZWOP', 'EXPWP', 'EXPWOP', 'DEXP',
];
const CREDIT_TERM_ROLES = ['OWNER', 'MANAGER'];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type AddressRow = { id?: number; label: string; address: string; isDefault: boolean };

type CustomerForm = {
  name: string;
  phone: string;
  email: string;
  gstin: string;
  state: string;
  pan: string;
  taxpayerType: TaxpayerType;
  billingAddress: string;
  shippingAddress: string;
  shippingAddresses: AddressRow[];
  pincode: string;
  latitude: string;
  longitude: string;
  creditLimit: string;
  creditDays: string;
  notes: string;
  whatsappOptIn: boolean;
  dunningOptOut: boolean;
  priceList: number | '';
  customFields: Record<string, string>;
};

const EMPTY_CUSTOMER_FORM: CustomerForm = {
  name: '',
  phone: '',
  email: '',
  gstin: '',
  state: '',
  pan: '',
  // No GSTIN yet: an unregistered buyer. A full GSTIN switches this to Regular unless the user chose.
  taxpayerType: 'UNREGISTERED',
  billingAddress: '',
  shippingAddress: '',
  shippingAddresses: [],
  pincode: '',
  latitude: '',
  longitude: '',
  creditLimit: '',
  creditDays: '',
  notes: '',
  whatsappOptIn: false,
  dunningOptOut: false,
  priceList: '',
  customFields: {},
};

function formFromCustomer(c: Customer | null): CustomerForm {
  if (!c) return EMPTY_CUSTOMER_FORM;
  return {
    name: c.name,
    phone: c.phone ?? '',
    email: c.email ?? '',
    gstin: c.gstin ?? '',
    state: c.state ?? '',
    pan: c.pan ?? '',
    taxpayerType: (c.taxpayerType as TaxpayerType) || 'REGULAR',
    billingAddress: c.billingAddress ?? '',
    shippingAddress: c.shippingAddress ?? '',
    shippingAddresses: (c.shippingAddresses ?? []).map((a: ShippingAddress) => ({
      id: a.id,
      label: a.label ?? '',
      address: a.address,
      isDefault: Boolean(a.isDefault),
    })),
    pincode: c.pincode ?? '',
    latitude: c.latitude ?? '',
    longitude: c.longitude ?? '',
    creditLimit: c.creditLimit != null && Number(c.creditLimit) !== 0 ? String(c.creditLimit) : '',
    creditDays: c.creditDays ? String(c.creditDays) : '',
    notes: c.notes ?? '',
    whatsappOptIn: Boolean(c.whatsappOptIn),
    dunningOptOut: Boolean(c.dunningOptOut),
    priceList: c.priceList ?? '',
    customFields: { ...(c.customFields ?? {}) },
  };
}

function coordinateProblem(latitude: string, longitude: string): string | null {
  const lat = latitude.trim();
  const lng = longitude.trim();
  if (!lat && !lng) return null;
  if (!lat || !lng) return t('osPlan.coordinatesPair');
  const la = Number(lat);
  const lo = Number(lng);
  if (!Number.isFinite(la) || !Number.isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) {
    return t('customers.coordinatesRange');
  }
  return null;
}

function nonNegative(text: string, integer: boolean): boolean {
  const v = text.trim();
  if (!v) return true;
  if (!/^\d+(\.\d{1,2})?$/.test(v)) return false;
  return integer ? /^\d+$/.test(v) : true;
}

type Props = {
  open: boolean;
  customer: Customer | null;
  onClose: () => void;
  onSaved: (saved: Customer) => void;
};

export function CustomerFormDialog({ open, customer, onClose, onSaved }: Props) {
  const { user } = useAuth();
  const editing = customer;
  const company = useQuery({ queryKey: ['company'], queryFn: getCompany, enabled: open });
  const priceLists = useQuery({ queryKey: ['price-lists'], queryFn: listPriceLists, enabled: open });
  const [form, setForm] = useState<CustomerForm>(EMPTY_CUSTOMER_FORM);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [nameTouched, setNameTouched] = useState(false);
  const [lookup, setLookup] = useState<GstinLookup | null>(null);
  const [stale, setStale] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const touched = useRef(new Set<string>());
  const stateTouched = useRef(false);
  const baseVersion = useRef<number | undefined>(undefined);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open && !wasOpen.current) {
      setForm(formFromCustomer(customer));
      setDialogError(null);
      setFieldErrors({});
      setNameTouched(false);
      setLookup(null);
      setStale(false);
      setLocationError(null);
      touched.current = new Set();
      stateTouched.current = false;
      baseVersion.current = customer?.version;
    }
    wasOpen.current = open;
  }, [open, customer]);

  const isWalkIn = Boolean(editing?.isPosWalkIn);
  const canEditCreditTerms = !!user && CREDIT_TERM_ROLES.includes(user.role) && !isWalkIn;
  const requirePlaceOfSupply = !!company.data?.isGstRegistered && !company.data?.assumeLocalStateForBlankParty;
  const placeOfSupplyOk = !requirePlaceOfSupply || placeOfSupplyKnown(form.state, form.gstin);
  const loadedPincode = (editing?.pincode ?? '').trim();
  const pincodeText = form.pincode.trim();
  // A stored legacy PIN may be saved again unchanged. A new or edited value must be a real PIN.
  const pincodeOk = (editing != null && pincodeText === loadedPincode) || isValidIndianPincode(form.pincode);
  const gstinText = form.gstin.trim();
  const gstinOk = !gstinText || isValidGstin(gstinText);
  const emailOk = !form.email.trim() || EMAIL_RE.test(form.email.trim());
  const phoneOk = !form.phone.trim() || isValidIndianPhone(form.phone);
  const coordsProblem = coordinateProblem(form.latitude, form.longitude);
  const creditLimitOk = nonNegative(form.creditLimit, false);
  const creditDaysOk = nonNegative(form.creditDays, true);
  const customFieldDefs = useMemo(
    () => activeCustomFieldDefs(company.data?.partyCustomFieldDefs),
    [company.data?.partyCustomFieldDefs],
  );
  const addressesOk = form.shippingAddresses.every((row) => row.address.trim() || !row.label.trim());
  const canSave =
    Boolean(form.name.trim()) &&
    partyNameError(form.name) == null &&
    placeOfSupplyOk &&
    phoneOk &&
    pincodeOk &&
    gstinOk &&
    emailOk &&
    coordsProblem == null &&
    creditLimitOk &&
    creditDaysOk &&
    addressesOk;

  const set = <K extends keyof CustomerForm>(key: K, value: CustomerForm[K]) => {
    touched.current.add(key);
    setFieldErrors((prev) => {
      if (!(key in prev)) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
    setForm((f) => ({ ...f, [key]: value }));
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const gstin = form.gstin.trim().toUpperCase();
      const payload: Partial<Customer> = {
        name: form.name.trim(),
        phone: form.phone,
        email: form.email.trim(),
        gstin,
        state: form.state,
        pan: form.pan.trim().toUpperCase(),
        taxpayerType: form.taxpayerType,
        billingAddress: form.billingAddress,
        shippingAddress: form.shippingAddress,
        shippingAddresses: form.shippingAddresses
          .filter((row) => row.address.trim())
          .map((row) => ({
            id: row.id,
            label: row.label.trim(),
            address: row.address.trim(),
            isDefault: row.isDefault,
          })),
        pincode: form.pincode.trim(),
        latitude: form.latitude.trim() || null,
        longitude: form.longitude.trim() || null,
        notes: form.notes,
        whatsappOptIn: form.whatsappOptIn,
        dunningOptOut: form.dunningOptOut,
        priceList: form.priceList === '' ? null : form.priceList,
        customFields: form.customFields,
      };
      if (canEditCreditTerms) {
        payload.creditLimit = form.creditLimit.trim() || '0';
        payload.creditDays = Number(form.creditDays.trim() || 0);
      }
      if (editing) return updateCustomer(editing.id, { ...payload, version: baseVersion.current });
      return createCustomer({ ...payload, status: 'ACTIVE' });
    },
    onSuccess: (saved) => {
      setDialogError(null);
      onSaved(saved);
      onClose();
    },
    onError: (err) => {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        setStale(true);
        setDialogError(null);
        return;
      }
      const details = getErrorDetails(err);
      const mapped: Record<string, string> = {};
      const unmatched: string[] = [];
      for (const [field, value] of Object.entries(details ?? {})) {
        const first = Array.isArray(value) ? value.find((v) => typeof v === 'string') : value;
        if (typeof first !== 'string') continue;
        if (field in EMPTY_CUSTOMER_FORM) mapped[field] = first;
        else unmatched.push(`${field}: ${first}`);
      }
      setFieldErrors(mapped);
      // A field the form does not have, or no field at all, still has to be said somewhere.
      setDialogError(unmatched.length ? unmatched.join('; ') : Object.keys(mapped).length ? null : getErrorMessage(err));
    },
  });

  const reloadLatest = useMutation({
    mutationFn: () => getCustomer(editing!.id),
    onSuccess: (latest) => {
      baseVersion.current = latest.version;
      const fresh = formFromCustomer(latest);
      // Keep what the user changed; take everything else from the saved row.
      setForm((current) => {
        const merged = { ...fresh } as Record<string, unknown>;
        for (const key of touched.current) merged[key] = (current as Record<string, unknown>)[key];
        return merged as CustomerForm;
      });
      setStale(false);
    },
    onError: (err) => setDialogError(getErrorMessage(err)),
  });

  const lookupMutation = useMutation({
    mutationFn: () => lookupCustomerGstin(form.gstin.trim().toUpperCase()),
    onSuccess: (result) => {
      setLookup(result);
      setDialogError(null);
      setForm((f) => ({
        ...f,
        state: result.state || f.state,
        pan: result.pan || f.pan,
        taxpayerType: (TAXPAYER_TYPES as string[]).includes(result.taxpayerType)
          ? (result.taxpayerType as TaxpayerType)
          : f.taxpayerType,
      }));
    },
    onError: (err) => setDialogError(getErrorMessage(err)),
  });

  const onGstinChange = (raw: string) => {
    const val = raw.toUpperCase().replace(/\s/g, '');
    const matchedState = getStateFromGstin(val);
    touched.current.add('gstin');
    setLookup(null);
    setFieldErrors((prev) => {
      const next = { ...prev };
      delete next.gstin;
      delete next.state;
      return next;
    });
    setForm((f) => {
      const complete = isValidGstin(val);
      const stateFromGstin = matchedState && (complete || !stateTouched.current) ? matchedState : f.state;
      return {
        ...f,
        gstin: val,
        state: stateFromGstin,
        pan: complete ? val.slice(2, 12) : f.pan,
        taxpayerType: touched.current.has('taxpayerType')
          ? f.taxpayerType
          : complete && f.taxpayerType === 'UNREGISTERED'
            ? 'REGULAR'
            : !val && f.taxpayerType === 'REGULAR'
              ? 'UNREGISTERED'
              : f.taxpayerType,
      };
    });
  };

  const updateAddress = (index: number, patch: Partial<AddressRow>) => {
    touched.current.add('shippingAddresses');
    setForm((f) => ({
      ...f,
      shippingAddresses: f.shippingAddresses.map((row, i) => {
        if (i === index) return { ...row, ...patch };
        return patch.isDefault ? { ...row, isDefault: false } : row;
      }),
    }));
  };

  const useMyLocation = () => {
    setLocationError(null);
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocationError(t('customers.locationFailed'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        touched.current.add('latitude');
        touched.current.add('longitude');
        setForm((f) => ({
          ...f,
          latitude: pos.coords.latitude.toFixed(6),
          longitude: pos.coords.longitude.toFixed(6),
        }));
      },
      () => setLocationError(t('customers.locationFailed')),
      { timeout: 10_000 },
    );
  };

  const nameInvalid = nameTouched && (!form.name.trim() || partyNameError(form.name) != null);
  const saveHint = !form.name.trim()
    ? t('customers.enterNameTooltip')
    : partyNameError(form.name)
      ? t('billing.partyNameInvalid')
      : !placeOfSupplyOk
        ? t('customers.stateOrGstinTooltip')
        : '';

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm" aria-labelledby="customer-form-title">
      <DialogTitle id="customer-form-title">
        {editing ? t('customers.editTitle') : t('customers.createTitle')}
        {isWalkIn ? <Chip size="small" color="info" label={t('customers.posWalkIn')} sx={{ ml: 1 }} /> : null}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {dialogError ? <HelpErrorAlert message={dialogError} /> : null}
          {stale ? (
            <Alert
              severity="warning"
              action={
                <Button color="inherit" size="small" disabled={reloadLatest.isPending} onClick={() => reloadLatest.mutate()}>
                  {t('customers.reloadLatest')}
                </Button>
              }
            >
              {t('customers.staleBody')}
            </Alert>
          ) : null}
          {isWalkIn ? <Alert severity="info">{t('customers.posWalkInLocked')}</Alert> : null}

          <TextField
            label={t('common.name')}
            required
            value={form.name}
            placeholder={t('billing.partyNamePrompt')}
            onBlur={() => setNameTouched(true)}
            error={nameInvalid || Boolean(fieldErrors.name)}
            helperText={
              fieldErrors.name ??
              (nameTouched && !form.name.trim()
                ? t('customers.nameRequired')
                : nameTouched && partyNameError(form.name)
                  ? t('billing.partyNameInvalid')
                  : undefined)
            }
            onChange={(e) => set('name', e.target.value)}
          />
          <TextField
            label={t('common.phone')}
            value={form.phone}
            error={!phoneOk || Boolean(fieldErrors.phone)}
            helperText={fieldErrors.phone ?? (!phoneOk ? t('customers.phoneInvalid') : undefined)}
            onChange={(e) => set('phone', e.target.value)}
          />
          <TextField
            label={t('common.email')}
            value={form.email}
            error={!emailOk || Boolean(fieldErrors.email)}
            helperText={fieldErrors.email ?? (!emailOk ? t('customers.emailInvalid') : undefined)}
            onChange={(e) => set('email', e.target.value)}
          />

          <Accordion defaultExpanded disableGutters variant="outlined">
            <AccordionSummary id="customer-section-tax-header" aria-controls="customer-section-tax-content">
              <Typography variant="subtitle2" component="span">{t('customers.sectionTax')}</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <Stack direction="row" spacing={1} alignItems="flex-start">
                  <TextField
                    fullWidth
                    label="GSTIN"
                    value={form.gstin}
                    disabled={isWalkIn}
                    error={!gstinOk || Boolean(fieldErrors.gstin)}
                    helperText={fieldErrors.gstin ?? (!gstinOk ? t('customers.gstinInvalid') : undefined)}
                    onChange={(e) => onGstinChange(e.target.value)}
                    inputProps={{ maxLength: 15 }}
                  />
                  <Button
                    variant="outlined"
                    sx={{ whiteSpace: 'nowrap', mt: 0.5 }}
                    disabled={isWalkIn || !gstinText || !gstinOk || lookupMutation.isPending}
                    onClick={() => lookupMutation.mutate()}
                  >
                    {t('customers.verifyAutofill')}
                  </Button>
                </Stack>
                {lookup ? (
                  <Stack spacing={1}>
                    {lookup.notice ? <Alert severity="info">{lookup.notice}</Alert> : null}
                    {lookup.existingCustomer && lookup.existingCustomer.id !== editing?.id ? (
                      <Alert severity="warning">
                        {t('customers.gstinTaken', { name: lookup.existingCustomer.name })}
                      </Alert>
                    ) : null}
                    {lookup.legalName && lookup.legalName !== form.name.trim() ? (
                      <Button size="small" onClick={() => set('name', lookup.legalName)}>
                        {t('customers.useLegalName', { name: lookup.legalName })}
                      </Button>
                    ) : null}
                  </Stack>
                ) : null}
                <StateSelect
                  value={form.state}
                  onChange={(state) => {
                    stateTouched.current = true;
                    set('state', state);
                  }}
                  required={requirePlaceOfSupply}
                  error={(requirePlaceOfSupply && !placeOfSupplyOk) || Boolean(fieldErrors.state)}
                  helperText={
                    fieldErrors.state ??
                    (requirePlaceOfSupply && !placeOfSupplyOk ? t('customers.stateOrGstinRequired') : undefined)
                  }
                />
                <TextField
                  label="PAN"
                  value={form.pan}
                  onChange={(e) => set('pan', e.target.value.toUpperCase())}
                  inputProps={{ maxLength: 10 }}
                />
                <TextField
                  select
                  label={t('customers.taxpayerType')}
                  value={form.taxpayerType}
                  onChange={(e) => set('taxpayerType', e.target.value as TaxpayerType)}
                >
                  {TAXPAYER_TYPES.map((type) => (
                    <MenuItem key={type} value={type}>
                      {t(`customers.taxpayer.${type}`)}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
            </AccordionDetails>
          </Accordion>

          <Accordion defaultExpanded disableGutters variant="outlined">
            <AccordionSummary id="customer-section-credit-header" aria-controls="customer-section-credit-content">
              <Typography variant="subtitle2" component="span">{t('customers.sectionCredit')}</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <TextField
                  label={t('customers.creditLimit')}
                  value={form.creditLimit}
                  disabled={!canEditCreditTerms}
                  error={!creditLimitOk || Boolean(fieldErrors.creditLimit)}
                  helperText={
                    fieldErrors.creditLimit ??
                    (!canEditCreditTerms ? t('customers.creditTermsLocked') : !creditLimitOk ? t('customers.numberInvalid') : undefined)
                  }
                  onChange={(e) => set('creditLimit', e.target.value)}
                  inputProps={{ inputMode: 'decimal' }}
                />
                <TextField
                  label={t('customers.creditDays')}
                  value={form.creditDays}
                  disabled={!canEditCreditTerms}
                  error={!creditDaysOk || Boolean(fieldErrors.creditDays)}
                  helperText={fieldErrors.creditDays ?? (!creditDaysOk ? t('customers.numberInvalid') : undefined)}
                  onChange={(e) => set('creditDays', e.target.value)}
                  inputProps={{ inputMode: 'numeric' }}
                />
                <TextField
                  select
                  label={t('sweep.priceList')}
                  value={form.priceList === '' ? '' : form.priceList}
                  onChange={(e) => set('priceList', e.target.value === '' ? '' : Number(e.target.value))}
                >
                  <MenuItem value="">{t('sweep2.none')}</MenuItem>
                  {(priceLists.data ?? []).map((pl) => (
                    <MenuItem key={pl.id} value={pl.id}>
                      {pl.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Stack>
            </AccordionDetails>
          </Accordion>

          <Accordion disableGutters variant="outlined">
            <AccordionSummary id="customer-section-address-header" aria-controls="customer-section-address-content">
              <Typography variant="subtitle2" component="span">{t('customers.sectionAddress')}</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                <TextField
                  label={t('sweep.billingAddress')}
                  value={form.billingAddress}
                  onChange={(e) => set('billingAddress', e.target.value)}
                />
                <TextField
                  label={t('customers.shippingAddress')}
                  value={form.shippingAddress}
                  onChange={(e) => set('shippingAddress', e.target.value)}
                />
                <TextField
                  label={t('osPlan.pincode')}
                  value={form.pincode}
                  onChange={(e) => set('pincode', e.target.value)}
                  error={(!pincodeOk && Boolean(pincodeText)) || Boolean(fieldErrors.pincode)}
                  helperText={fieldErrors.pincode ?? (!pincodeOk || !pincodeText ? t('validation.pincode') : undefined)}
                  inputProps={{ maxLength: 10, inputMode: 'numeric' }}
                />
                <Typography variant="body2" color="text.secondary">
                  {t('customers.extraAddresses')}
                </Typography>
                {form.shippingAddresses.map((row, index) => (
                  <Stack key={row.id ?? `new-${index}`} direction="row" spacing={1} alignItems="flex-start">
                    <TextField
                      size="small"
                      label={t('customers.addressLabel')}
                      value={row.label}
                      onChange={(e) => updateAddress(index, { label: e.target.value })}
                      sx={{ width: 140 }}
                    />
                    <TextField
                      size="small"
                      fullWidth
                      label={t('customers.addressText')}
                      value={row.address}
                      onChange={(e) => updateAddress(index, { address: e.target.value })}
                    />
                    <FormControlLabel
                      control={
                        <Checkbox
                          size="small"
                          checked={row.isDefault}
                          onChange={(e) => updateAddress(index, { isDefault: e.target.checked })}
                        />
                      }
                      label={t('customers.defaultAddress')}
                    />
                    <Button
                      size="small"
                      color="error"
                      onClick={() => {
                        touched.current.add('shippingAddresses');
                        setForm((f) => ({ ...f, shippingAddresses: f.shippingAddresses.filter((_r, i) => i !== index) }));
                      }}
                    >
                      {t('customers.removeAddress')}
                    </Button>
                  </Stack>
                ))}
                <Button
                  size="small"
                  sx={{ alignSelf: 'flex-start' }}
                  onClick={() => {
                    touched.current.add('shippingAddresses');
                    setForm((f) => ({
                      ...f,
                      shippingAddresses: [...f.shippingAddresses, { label: '', address: '', isDefault: false }],
                    }));
                  }}
                >
                  {t('customers.addAddress')}
                </Button>
                <TextField
                  label={t('osPlan.latitude')}
                  value={form.latitude}
                  onChange={(e) => set('latitude', e.target.value)}
                  error={coordsProblem != null}
                  helperText={t('customers.coordinatesHelper')}
                  inputProps={{ inputMode: 'decimal' }}
                />
                <TextField
                  label={t('osPlan.longitude')}
                  value={form.longitude}
                  onChange={(e) => set('longitude', e.target.value)}
                  error={coordsProblem != null}
                  helperText={coordsProblem ?? t('customers.coordinatesHelper')}
                  inputProps={{ inputMode: 'decimal' }}
                />
                <Button size="small" sx={{ alignSelf: 'flex-start' }} onClick={useMyLocation}>
                  {t('customers.useLocation')}
                </Button>
                {locationError ? <Typography variant="caption" color="error">{locationError}</Typography> : null}
              </Stack>
            </AccordionDetails>
          </Accordion>

          <Accordion disableGutters variant="outlined">
            <AccordionSummary id="customer-section-other-header" aria-controls="customer-section-other-content">
              <Typography variant="subtitle2" component="span">{t('customers.sectionOther')}</Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={2}>
                {customFieldDefs.map((def) => (
                  <TextField
                    key={def.key}
                    label={def.label}
                    value={form.customFields[def.key] ?? ''}
                    onChange={(e) => set('customFields', { ...form.customFields, [def.key]: e.target.value })}
                  />
                ))}
                <TextField
                  label={t('customers.notes')}
                  value={form.notes}
                  multiline
                  minRows={2}
                  onChange={(e) => set('notes', e.target.value)}
                />
                <FormControlLabel
                  control={<Checkbox checked={form.whatsappOptIn} onChange={(e) => set('whatsappOptIn', e.target.checked)} />}
                  label={t('common.whatsappOptIn')}
                />
                <Typography variant="caption" color="text.secondary">
                  {t('common.whatsappOptInHelp')}
                </Typography>
                <FormControlLabel
                  control={<Checkbox checked={form.dunningOptOut} onChange={(e) => set('dunningOptOut', e.target.checked)} />}
                  label={t('settings.dunningOptOut')}
                />
              </Stack>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Tooltip title={saveHint}>
          <span>
            <Button
              variant="contained"
              disabled={!canSave || saveMutation.isPending || stale}
              onClick={() => saveMutation.mutate()}
            >
              {t('common.save')}
            </Button>
          </span>
        </Tooltip>
      </DialogActions>
    </Dialog>
  );
}
