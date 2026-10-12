import { useState } from 'react';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import RemoveIcon from '@mui/icons-material/Remove';
import { t } from '@/i18n';
import { formatMoney } from '@/utils/money';
import { formatQuantity, parseQuantity, quantityPolicy } from '@/utils/quantity';
import type { QuickLine } from './types';

const TOUCH = { width: 44, height: 44 } as const;

/** One order line: name + SKU, price per unit, a typeable quantity with +/- and a separate delete. */
export function QuickLineRow({
  line,
  stockBlocks = true,
  onQuantity,
  onRemove,
}: {
  line: QuickLine;
  /** The company blocks negative stock, so a short line is a hard stop (otherwise it is only a heads-up). */
  stockBlocks?: boolean;
  onQuantity: (key: string, quantity: number) => void;
  onRemove: (key: string) => void;
}) {
  const policy = quantityPolicy(line.uqc);
  const [text, setText] = useState(formatQuantity(line.quantity));
  const [invalid, setInvalid] = useState(false);
  const [seenQuantity, setSeenQuantity] = useState(line.quantity);

  // Keep the box in step when +/- or a repeat tap changes the quantity from outside.
  if (seenQuantity !== line.quantity) {
    setSeenQuantity(line.quantity);
    setText(formatQuantity(line.quantity));
    setInvalid(false);
  }

  const commit = () => {
    const parsed = parseQuantity(text, policy);
    if (parsed == null) {
      setInvalid(true);
      setText(formatQuantity(line.quantity));
      return;
    }
    setInvalid(false);
    if (parsed !== line.quantity) onQuantity(line.key, parsed);
  };

  const step = policy.decimals ? policy.step : 1;
  const lowStock = line.trackInventory && line.availableQty != null && line.quantity > line.availableQty;

  return (
    <Paper sx={{ p: 1.25, display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ minWidth: 0 }}>
        <Typography fontWeight={600} sx={{ overflowWrap: 'anywhere' }}>
          {line.name}
        </Typography>
        <Typography variant="caption" color="text.secondary" component="div">
          {line.sku ? `${line.sku} · ` : ''}
          {formatMoney(line.unitPrice)} / {line.unitName || t('quickEntry.each')} ·{' '}
          <strong>{formatMoney(line.quantity * line.unitPrice)}</strong>
        </Typography>
        {line.priceListName ? <Chip size="small" label={line.priceListName} sx={{ mt: 0.5 }} /> : null}
        {lowStock ? (
          <Chip
            size="small"
            color={stockBlocks ? 'warning' : 'info'}
            label={t('quickEntry.lowStock', { n: formatQuantity(line.availableQty ?? 0) })}
            sx={{ mt: 0.5, ml: line.priceListName ? 0.5 : 0 }}
          />
        ) : null}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <IconButton
        sx={TOUCH}
        disabled={line.quantity - step < policy.min}
        onClick={() => onQuantity(line.key, Math.max(policy.min, Math.round((line.quantity - step) * 1000) / 1000))}
        aria-label={`${t('quickEntry.decrease')} ${line.name}`}
      >
        <RemoveIcon fontSize="small" />
      </IconButton>
      <TextField
        size="small"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit();
        }}
        error={invalid}
        helperText={invalid ? t('quickEntry.minQty', { n: formatQuantity(policy.min) }) : undefined}
        inputProps={{
          inputMode: policy.decimals ? 'decimal' : 'numeric',
          'aria-label': t('quickEntry.quantityFor', { name: line.name }),
          style: { textAlign: 'center', width: 56 },
        }}
      />
      <IconButton
        sx={TOUCH}
        onClick={() => onQuantity(line.key, Math.round((line.quantity + step) * 1000) / 1000)}
        aria-label={`${t('quickEntry.increase')} ${line.name}`}
      >
        <AddIcon fontSize="small" />
      </IconButton>
      <Box sx={{ flex: 1 }} />
      <IconButton
        sx={{ ...TOUCH, ml: 1 }}
        onClick={() => onRemove(line.key)}
        aria-label={t('quickEntry.removeLine', { name: line.name })}
      >
        <DeleteIcon fontSize="small" />
      </IconButton>
      </Box>
    </Paper>
  );
}
