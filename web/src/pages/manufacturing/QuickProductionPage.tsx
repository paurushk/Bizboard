import { useMemo, useState } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link as RouterLink } from 'react-router-dom';
import { getCanMake, listRecipes, quickProduction, type WorkOrderRow } from '@/api/mfg';
import { t } from '@/i18n';
import { ErrorLine, MfgPage, NumField, ProductPick, Stat, WarehousePick, qty, todayIso, useMfgRights, useMasters, useRun } from './mfgShared';

/** One screen for "I made 50 of these": item, quantity, date. The server uses the active recipe. */
export function QuickProductionPage() {
  const qc = useQueryClient();
  const { canWork } = useMfgRights();
  const { productName } = useMasters();
  const { run, busy, error, clear } = useRun();
  const [product, setProduct] = useState<number | ''>('');
  const [quantity, setQuantity] = useState('');
  const [docDate, setDocDate] = useState(todayIso());
  const [batchNo, setBatchNo] = useState('');
  const [expDate, setExpDate] = useState('');
  const [fgWarehouse, setFgWarehouse] = useState<number | ''>('');
  const [notes, setNotes] = useState('');
  const [made, setMade] = useState<WorkOrderRow | null>(null);
  // One key per distinct request: pressing the button twice, or a network retry, makes one order. Changing
  // anything in the form is a different request, so it gets a new key (the server refuses one key on two bodies).
  const [attemptKey, setAttemptKey] = useState(() => crypto.randomUUID());
  const edits = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setAttemptKey(crypto.randomUUID());
  };

  const recipes = useQuery({
    queryKey: ['mfg-recipes-active', product],
    queryFn: () => listRecipes({ product: product as number, status: 'ACTIVE' }),
    enabled: product !== '',
  });
  const canMake = useQuery({
    queryKey: ['mfg-can-make', product],
    queryFn: () => getCanMake(product as number),
    enabled: product !== '' && (recipes.data?.length ?? 0) > 0,
  });
  const noRecipe = product !== '' && recipes.isSuccess && recipes.data.length === 0;
  const tooMuch = useMemo(() => {
    if (!canMake.data || !quantity) return false;
    return Number(quantity) > Number(canMake.data.qty);
  }, [canMake.data, quantity]);

  const submit = async () => {
    if (product === '' || !quantity) return;
    const result = await run(() =>
      quickProduction(
        {
          product,
          qty: quantity,
          docDate,
          batchNo: batchNo || undefined,
          expDate: expDate || undefined,
          fgWarehouse: fgWarehouse === '' ? undefined : fgWarehouse,
          notes: notes || undefined,
        },
        attemptKey,
      ),
    );
    if (result) {
      setMade(result);
      setAttemptKey(crypto.randomUUID());
      setQuantity('');
      setBatchNo('');
      setNotes('');
      void qc.invalidateQueries({ queryKey: ['mfg-work-orders'] });
      void qc.invalidateQueries({ queryKey: ['mfg-can-make'] });
    }
  };

  return (
    <MfgPage title={t('mfg.quick.title')} subtitle={t('mfg.quick.subtitle')}>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2} sx={{ maxWidth: 720 }}>
          <ErrorLine error={error} onClose={clear} />
          {made ? (
            <Alert severity="success" onClose={() => setMade(null)}>
              {t('mfg.quick.done', { number: made.number, item: made.productName })}{' '}
              <RouterLink to={`/manufacturing/work-orders/${made.id}`}>{t('mfg.quick.open')}</RouterLink>
            </Alert>
          ) : null}
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <ProductPick label={t('mfg.quick.item')} value={product} onChange={edits(setProduct)} required />
            <NumField label={t('mfg.common.quantity')} value={quantity} onChange={edits(setQuantity)} />
            <TextField size="small" type="date" label={t('mfg.common.date')} value={docDate} onChange={(e) => edits(setDocDate)(e.target.value)} InputLabelProps={{ shrink: true }} />
          </Stack>
          {noRecipe ? <Alert severity="warning">{t('mfg.quick.noRecipe', { item: productName(product as number) })}</Alert> : null}
          {canMake.data && product !== '' ? (
            <Stack direction="row" spacing={2}>
              <Stat label={t('mfg.quick.canMake')} value={qty(canMake.data.qty)} tone={tooMuch ? 'bad' : 'good'} />
              {canMake.data.limitedByName ? <Stat label={t('mfg.quick.limitedBy')} value={canMake.data.limitedByName} /> : null}
            </Stack>
          ) : null}
          {tooMuch ? <Alert severity="warning">{t('mfg.quick.moreThanStock')}</Alert> : null}
          <Typography variant="subtitle2" color="text.secondary">
            {t('mfg.quick.optional')}
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField size="small" label={t('mfg.common.batchNo')} value={batchNo} onChange={(e) => edits(setBatchNo)(e.target.value)} />
            <TextField size="small" type="date" label={t('mfg.common.expiry')} value={expDate} onChange={(e) => edits(setExpDate)(e.target.value)} InputLabelProps={{ shrink: true }} />
            <WarehousePick label={t('mfg.quick.putAwayIn')} value={fgWarehouse} onChange={edits(setFgWarehouse)} />
          </Stack>
          <TextField size="small" label={t('mfg.common.notes')} value={notes} onChange={(e) => edits(setNotes)(e.target.value)} />
          <Stack direction="row" spacing={2}>
            <Button variant="contained" disabled={!canWork || busy || product === '' || !quantity || noRecipe} onClick={submit}>
              {t('mfg.quick.record')}
            </Button>
            <Button component={RouterLink} to="/manufacturing/work-orders">
              {t('mfg.quick.useWorkOrder')}
            </Button>
          </Stack>
        </Stack>
      </Paper>
    </MfgPage>
  );
}
