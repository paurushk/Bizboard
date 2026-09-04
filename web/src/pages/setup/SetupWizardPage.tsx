import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  FormControlLabel,
  FormLabel,
  LinearProgress,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
} from '@mui/material';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { PreventionNote } from '@/pages/help/PreventionNote';
import {
  completeSalesInvoice,
  createCustomer,
  createOpeningStock,
  createProduct,
  createSalesInvoice,
  getCompany,
  listCustomers,
  listProducts,
  updateCompany,
} from '@/api/resources';
import { getErrorMessage } from '@/api/client';
import { todayIso } from '@/components/billing';
import { useAuth } from '@/auth/AuthContext';
import { isSetupWizardEnabled } from '@/config/features';
import { t } from '@/i18n';
import { trackOnboardingEvent } from '@/onboarding/analytics';
import { preferredInvoiceType } from '@/onboarding/taxHints';
import type { RegistrationType } from '@/types/domain';
import { HelpErrorAlert } from '@/pages/help/HelpErrorAlert';

const STEP_KEYS = ['tax', 'shop', 'payments', 'catalog', 'first_bill'] as const;
type StepKey = (typeof STEP_KEYS)[number];

const SAMPLE_PRODUCTS = [
  { name: 'Sample Item', sku: 'SAMPLE-ITEM', sellingPrice: 100, gstRate: 18 },
  { name: 'Sample Service', sku: 'SAMPLE-SERVICE', sellingPrice: 500, gstRate: 18 },
  { name: 'Delivery Charge', sku: 'SAMPLE-DELIVERY', sellingPrice: 50, gstRate: 0 },
];

function stepIndex(value: string | null | undefined, fallback = 0): number {
  const index = STEP_KEYS.indexOf(value as StepKey);
  return index >= 0 ? index : fallback;
}

export function SetupWizardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedStep = searchParams.get('step');
  const companyQuery = useQuery({ queryKey: ['company'], queryFn: getCompany });
  const productsQuery = useQuery({ queryKey: ['setup-products'], queryFn: () => listProducts() });
  const lastCreatedProductId = useRef<number | null>(null);
  const startedRef = useRef(false);
  const [activeStep, setActiveStep] = useState(() => stepIndex(requestedStep));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completedInvoiceId, setCompletedInvoiceId] = useState<number | null>(null);
  const [registrationType, setRegistrationType] = useState<RegistrationType>('UNREGISTERED');
  const [gstin, setGstin] = useState('');
  const [shop, setShop] = useState({ address: '', city: '', pincode: '' });
  const [payments, setPayments] = useState({ bankAccount: '', upiId: '' });
  const [product, setProduct] = useState({
    name: '',
    sellingPrice: '',
    gstRate: '18',
    hsnCode: '',
    openingQty: '',
  });

  const company = companyQuery.data;
  const products = productsQuery.data ?? [];
  const labels = useMemo(() => STEP_KEYS.map((key) => t(`setup.steps.${key}`)), []);

  useEffect(() => {
    if (!company) return;
    setRegistrationType(company.registrationType);
    setGstin(company.gstin ?? '');
    setShop({
      address: company.address ?? '',
      city: company.city ?? '',
      pincode: company.pincode ?? '',
    });
    setPayments({
      bankAccount: company.bankAccount ?? '',
      upiId: company.upiId ?? '',
    });
    if (!requestedStep) {
      setActiveStep(stepIndex(company.onboarding?.uiStep ?? company.onboarding?.step));
    }
  }, [company, requestedStep]);

  useEffect(() => {
    if (!company || startedRef.current || company.onboarding?.started) return;
    startedRef.current = true;
    void updateCompany({ markOnboardingStarted: true }).catch((err) => {
      startedRef.current = false;
      setError(getErrorMessage(err));
    });
  }, [company]);

  useEffect(() => {
    trackOnboardingEvent('setup_step_view', { step: STEP_KEYS[activeStep] });
  }, [activeStep]);

  if (!isSetupWizardEnabled() || user?.role !== 'OWNER') return <Navigate to="/" replace />;
  if (companyQuery.isLoading) {
    return <Box minHeight="100vh" display="grid" sx={{ placeItems: 'center' }}><CircularProgress /></Box>;
  }
  if (companyQuery.isError || !company) {
    return <Box p={3}><HelpErrorAlert error={companyQuery.error} /></Box>;
  }

  const moveTo = (next: number) => {
    setError(null);
    setActiveStep(next);
    setSearchParams({ step: STEP_KEYS[next] }, { replace: true });
  };

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const finishStep = async (key: StepKey, work?: () => Promise<void>) => {
    await run(async () => {
      await work?.();
      trackOnboardingEvent('setup_step_complete', { step: key });
      await queryClient.invalidateQueries({ queryKey: ['company'] });
      if (activeStep < STEP_KEYS.length - 1) moveTo(activeStep + 1);
    });
  };

  const saveTax = () => {
    if (registrationType === 'REGULAR' && !gstin.trim()) {
      setError(t('setup.errors.gstinRequired'));
      return;
    }
    void finishStep('tax', async () => {
      await updateCompany({
        registrationType,
        gstin: gstin.trim(),
        confirmTaxProfile: true,
        markOnboardingStarted: true,
      });
    });
  };

  const saveShop = () => {
    if (!shop.address.trim()) {
      setError(t('setup.errors.addressRequired'));
      return;
    }
    void finishStep('shop', async () => {
      await updateCompany({
        address: shop.address.trim(),
        city: shop.city.trim(),
        pincode: shop.pincode.trim(),
      });
    });
  };

  const savePayments = () =>
    void finishStep('payments', async () => {
      await updateCompany({
        bankAccount: payments.bankAccount.trim(),
        upiId: payments.upiId.trim(),
      });
    });

  const addProduct = () => {
    if (!product.name.trim() || Number(product.sellingPrice) <= 0) {
      setError(t('setup.errors.productRequired'));
      return;
    }
    if (registrationType === 'REGULAR' && !product.hsnCode.trim()) {
      setError(t('setup.errors.hsnRequired'));
      return;
    }
    void finishStep('catalog', async () => {
      const created = await createProduct({
        name: product.name.trim(),
        sku: `SETUP-${Date.now().toString(36).toUpperCase()}`,
        sellingPrice: Number(product.sellingPrice),
        purchasePrice: 0,
        gstRate: Number(product.gstRate) || 0,
        hsnCode: product.hsnCode.trim() || undefined,
        reorderLevel: 0,
        status: 'ACTIVE',
      });
      lastCreatedProductId.current = created.id;
      if (Number(product.openingQty) > 0) {
        await createOpeningStock({ product: created.id, quantity: Number(product.openingQty) });
      }
      await productsQuery.refetch();
      await queryClient.invalidateQueries({ queryKey: ['products'] });
      await queryClient.invalidateQueries({ queryKey: ['products-count'] });
    });
  };

  const addSamples = () => {
    // F3-034: these are real catalog rows, not throwaway fixtures — make the
    // user opt in, and tag each one (SAMPLE- SKU + description) so they are easy
    // to find and bulk-delete from Products later.
    if (!window.confirm(t('setup.addSamplesConfirm'))) return;
    void finishStep('catalog', async () => {
      await Promise.all(
        SAMPLE_PRODUCTS.map((sample) =>
          createProduct({
            ...sample,
            description: 'Sample data — safe to delete once you have added your own products.',
            purchasePrice: 0,
            reorderLevel: 0,
            status: 'ACTIVE',
            hsnCode: registrationType === 'REGULAR' ? '9999' : undefined,
          }),
        ),
      );
      await productsQuery.refetch();
      await queryClient.invalidateQueries({ queryKey: ['products-count'] });
    });
  };

  const continueCatalog = () => {
    if (products.length === 0) {
      setError(t('setup.errors.catalogRequired'));
      return;
    }
    trackOnboardingEvent('setup_step_complete', { step: 'catalog', existing: true });
    moveTo(4);
  };

  const createFirstBill = () =>
    void run(async () => {
      const latestProducts = await listProducts();
      const firstProduct =
        latestProducts.find((item) => item.id === lastCreatedProductId.current) ??
        latestProducts[latestProducts.length - 1] ??
        latestProducts[0];
      if (!firstProduct) throw new Error(t('setup.errors.catalogRequired'));
      const customers = await listCustomers();
      const customer =
        customers.find((item) => item.name.toLowerCase() === 'walk-in customer') ??
        (await createCustomer({ name: 'Walk-in Customer', state: company.state, status: 'ACTIVE' }));
      const invoice = await createSalesInvoice({
        customer: customer.id,
        invoiceType: preferredInvoiceType(registrationType),
        invoiceDate: todayIso(),
        items: [{
          product: firstProduct.id,
          quantity: 1,
          unitPrice: firstProduct.sellingPrice,
          gstRate: registrationType === 'REGULAR' ? firstProduct.gstRate : 0,
          hsnCode: firstProduct.hsnCode,
        }],
      });
      const completed = await completeSalesInvoice(invoice.id);
      setCompletedInvoiceId(completed.id);
      trackOnboardingEvent('setup_step_complete', { step: 'first_bill' });
      trackOnboardingEvent('setup_first_bill_complete', { invoiceId: completed.id });
      await queryClient.invalidateQueries({ queryKey: ['company'] });
      await queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    });

  const dismiss = () =>
    void run(async () => {
      await updateCompany({ dismissOnboarding: true });
      trackOnboardingEvent('setup_skip', { step: STEP_KEYS[activeStep] });
      await queryClient.invalidateQueries({ queryKey: ['company'] });
      navigate('/', { replace: true });
    });

  const primary = activeStep === 0
    ? { label: t('setup.saveContinue'), action: saveTax }
    : activeStep === 1
      ? { label: t('setup.saveContinue'), action: saveShop }
      : activeStep === 2
        ? { label: t('setup.saveContinue'), action: savePayments }
        : activeStep === 3
          ? { label: products.length ? t('setup.continue') : t('setup.addProduct'), action: products.length ? continueCatalog : addProduct }
          : { label: t('setup.createFirstBill'), action: createFirstBill };

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', pb: { xs: 10, sm: 4 } }}>
      <Box sx={{ bgcolor: 'primary.dark', color: 'primary.contrastText', px: { xs: 2, sm: 4 }, py: 2 }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" gap={2}>
          <Box>
            <Typography variant="h5" fontWeight={700}>{t('setup.title')}</Typography>
            <Typography variant="body2" sx={{ opacity: 0.85 }}>{t('setup.subtitle')}</Typography>
          </Box>
          <Button color="inherit" disabled={busy} onClick={dismiss}>{t('setup.skipForNow')}</Button>
        </Stack>
      </Box>
      <LinearProgress variant="determinate" value={((activeStep + 1) / STEP_KEYS.length) * 100} />

      <Box sx={{ maxWidth: 960, mx: 'auto', p: { xs: 2, sm: 4 } }}>
        <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 4, display: { xs: 'none', sm: 'flex' } }}>
          {labels.map((label) => <Step key={label}><StepLabel>{label}</StepLabel></Step>)}
        </Stepper>
        <Typography variant="overline" color="primary">{t('setup.progress', { current: activeStep + 1, total: 5 })}</Typography>
        <Paper sx={{ p: { xs: 2.5, sm: 4 }, mt: 1 }}>
          <Stack spacing={2.5}>
            <Typography variant="h4">{labels[activeStep]}</Typography>
            <Typography color="text.secondary">{t(`setup.descriptions.${STEP_KEYS[activeStep]}`)}</Typography>
            {error ? <HelpErrorAlert message={error} /> : null}

            {activeStep === 0 ? (
              <>
                <FormControl>
                  <FormLabel>{t('setup.registrationType')}</FormLabel>
                  <PreventionNote intent="registration-type" slot="signup-registration-type" />
                  <RadioGroup value={registrationType} onChange={(e) => setRegistrationType(e.target.value as RegistrationType)}>
                    <FormControlLabel value="UNREGISTERED" control={<Radio />} label={t('setup.unregistered')} />
                    <FormControlLabel value="REGULAR" control={<Radio />} label={t('setup.regular')} />
                    <FormControlLabel value="COMPOSITION" control={<Radio />} label={t('setup.composition')} />
                  </RadioGroup>
                </FormControl>
                {registrationType !== 'UNREGISTERED' ? (
                  <TextField
                    label={t('setup.gstin')}
                    required={registrationType === 'REGULAR'}
                    value={gstin}
                    inputProps={{ maxLength: 15 }}
                    onChange={(e) => setGstin(e.target.value.toUpperCase())}
                    helperText={registrationType === 'COMPOSITION' ? t('setup.gstinOptional') : undefined}
                  />
                ) : null}
              </>
            ) : null}

            {activeStep === 1 ? (
              <>
                <TextField label={t('setup.address')} required multiline minRows={2} value={shop.address} onChange={(e) => setShop((v) => ({ ...v, address: e.target.value }))} />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField fullWidth label={t('setup.city')} value={shop.city} onChange={(e) => setShop((v) => ({ ...v, city: e.target.value }))} />
                  <TextField fullWidth label={t('setup.pincode')} value={shop.pincode} onChange={(e) => setShop((v) => ({ ...v, pincode: e.target.value }))} />
                </Stack>
                <Alert severity="info">{t('setup.stateFromRegistration', { state: company.state })}</Alert>
              </>
            ) : null}

            {activeStep === 2 ? (
              <>
                <TextField label={t('setup.bankAccount')} value={payments.bankAccount} onChange={(e) => setPayments((v) => ({ ...v, bankAccount: e.target.value }))} />
                <TextField label={t('setup.upiId')} value={payments.upiId} onChange={(e) => setPayments((v) => ({ ...v, upiId: e.target.value }))} />
                <Button onClick={() => { trackOnboardingEvent('setup_step_complete', { step: 'payments', skipped: true }); moveTo(3); }}>{t('setup.skipOptional')}</Button>
              </>
            ) : null}

            {activeStep === 3 ? (
              <>
                {products.length ? <Alert severity="success">{t('setup.productsReady', { count: products.length })}</Alert> : null}
                <TextField label={t('setup.productName')} required value={product.name} onChange={(e) => setProduct((v) => ({ ...v, name: e.target.value }))} />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField fullWidth label={t('setup.sellingPrice')} required type="number" value={product.sellingPrice} onChange={(e) => setProduct((v) => ({ ...v, sellingPrice: e.target.value }))} />
                  <TextField fullWidth label={t('setup.gstRate')} type="number" value={product.gstRate} onChange={(e) => setProduct((v) => ({ ...v, gstRate: e.target.value }))} />
                </Stack>
                {registrationType === 'REGULAR' ? <TextField label={t('setup.hsnCode')} required value={product.hsnCode} onChange={(e) => setProduct((v) => ({ ...v, hsnCode: e.target.value }))} /> : null}
                <TextField label={t('setup.openingQty')} type="number" value={product.openingQty} onChange={(e) => setProduct((v) => ({ ...v, openingQty: e.target.value }))} />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                  <Button variant="outlined" onClick={addSamples} disabled={busy}>{t('setup.addSamples')}</Button>
                  <Button component={RouterLink} to="/settings/import?kind=PRODUCTS&return=/setup?step=catalog" variant="outlined">{t('setup.importProducts')}</Button>
                </Stack>
                <Alert severity="warning">{t('setup.addSamplesWarning')}</Alert>
              </>
            ) : null}

            {activeStep === 4 ? (
              completedInvoiceId ? (
                <Stack alignItems="center" textAlign="center" spacing={2} sx={{ py: 3 }}>
                  <CheckCircleOutlineIcon color="success" sx={{ fontSize: 72 }} />
                  <Typography variant="h4">{t('setup.completeTitle')}</Typography>
                  <Typography color="text.secondary">{t('setup.completeDescription')}</Typography>
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                    <Button component={RouterLink} to={`/sales/history/${completedInvoiceId}`} variant="outlined">{t('setup.viewInvoice')}</Button>
                    <Button component={RouterLink} to="/" variant="contained">{t('setup.goDashboard')}</Button>
                  </Stack>
                </Stack>
              ) : (
                <Alert severity="info">{t(`setup.firstBill.${registrationType === 'REGULAR' ? 'regular' : 'bos'}`)}</Alert>
              )
            ) : null}

            {!completedInvoiceId ? (
              <Stack direction="row" justifyContent="space-between" sx={{ display: { xs: 'none', sm: 'flex' } }}>
                <Button disabled={activeStep === 0 || busy} onClick={() => moveTo(activeStep - 1)}>{t('common.back')}</Button>
                <Button variant="contained" size="large" disabled={busy || productsQuery.isLoading} onClick={primary.action}>
                  {busy ? <CircularProgress size={22} color="inherit" /> : primary.label}
                </Button>
              </Stack>
            ) : null}
          </Stack>
        </Paper>
      </Box>

      {!completedInvoiceId ? (
        <Paper elevation={6} sx={{ display: { sm: 'none' }, position: 'fixed', bottom: 0, insetInline: 0, p: 1.5, zIndex: 10 }}>
          <Stack direction="row" spacing={1}>
            {activeStep > 0 ? <Button onClick={() => moveTo(activeStep - 1)}>{t('common.back')}</Button> : null}
            <Button fullWidth variant="contained" disabled={busy || productsQuery.isLoading} onClick={primary.action}>
              {busy ? <CircularProgress size={22} color="inherit" /> : primary.label}
            </Button>
          </Stack>
        </Paper>
      ) : null}
    </Box>
  );
}
