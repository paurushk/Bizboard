import type { ReactNode } from 'react';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { HelpRichText } from './HelpRichText';

export interface FaqItem {
  id: string;
  category: string;
  question: string;
  /** Extra words to match on in search (not shown). */
  keywords?: string[];
  answer: ReactNode;
}

/** Category display order on the Help page. */
export const FAQ_CATEGORIES: string[] = [
  'Items & Units',
  'Stock & Godowns',
];

const para = (text: string): ReactNode => <HelpRichText text={text} />;

export const FAQ_ITEMS: FaqItem[] = [
  {
    id: 'unit-conversion-rate',
    category: 'Items & Units',
    question: 'How do I set the conversion rate between a base unit and an alternate unit?',
    keywords: ['carton', 'pieces', 'pcs', 'box', 'uom', 'unit of measure', 'alternate unit', 'conversion'],
    answer: (
      <Stack spacing={1.5}>
        {para(
          'The conversion rate is how many **base** units sit in **one** alternate unit. Stock is always stored in the base unit. When you bill in the alternate unit, quantity × conversion rate is what stock uses, and price ÷ conversion rate is the per-base-unit cost.',
        )}
        {para(
          'Example — one carton holds 50 pieces: set base unit to PCS, alternate to CARTON, conversion rate `50`. Buying 3 CARTON then adds 150 PCS. A ₹1000 carton costs ₹20 per piece.',
        )}
        {para(
          'Make the base unit the smallest unit you count in (PCS) and the alternate the bulk unit you buy in (CARTON). Keeping CARTON as the base works too, but on-hand can then show fractional cartons (for example 7.34).',
        )}
        {para('The conversion rate must always be greater than 0.')}
      </Stack>
    ),
  },
  {
    id: 'base-vs-alternate-unit',
    category: 'Items & Units',
    question: 'What is the difference between the base unit and the alternate unit?',
    keywords: ['secondary unit', 'billing unit', 'stock unit'],
    answer: (
      <Stack spacing={1.5}>
        {para(
          'The **base unit** (Unit of Measure) is the unit your stock is counted and valued in. Every stock report, valuation and low-stock alert is in this unit.',
        )}
        {para(
          'The **alternate unit** is an optional second unit you can pick on a sales or purchase line — for example, stock an item in PCS but sell it by BOX. The line is converted back to base units using the conversion rate before stock is updated.',
        )}
        {para(
          'Pick the base unit carefully: once an item has any stock movement, the base unit is locked (you would have to reverse the stock to change it).',
        )}
      </Stack>
    ),
  },
  {
    id: 'unit-field-blank-on-edit',
    category: 'Items & Units',
    question: 'Why is the Unit of Measure field blank or greyed out when I edit an item?',
    keywords: ['disabled', 'locked', 'cannot change unit', 'imported item unit'],
    answer: (
      <Stack spacing={1.5}>
        <Typography variant="body2">Two common reasons:</Typography>
        {para(
          '1. **The item already has stock movements.** The base unit is locked after the first movement so historical quantities stay meaningful. To change quantities, use a stock adjustment; to change the unit itself, reverse the stock first.',
        )}
        {para(
          '2. **The item was created by import or API with a unit that is not in the standard list** (for example `pc` instead of `PCS`). The dropdown now shows the item’s own stored unit as an option, so the real value is always visible and is never silently replaced when you save.',
        )}
      </Stack>
    ),
  },
  {
    id: 'stock-shows-but-insufficient',
    category: 'Stock & Godowns',
    question:
      'The Products list shows stock available, but billing says "insufficient stock". Why?',
    keywords: ['available 0', 'godown', 'warehouse', 'negative stock', 'complete invoice'],
    answer: (
      <Stack spacing={1.5}>
        {para(
          'The **Available Stock** column on the Products list is a company-wide total across **all** godowns. A sales invoice draws stock from **one** godown — the one selected on the invoice (or the default godown if none is chosen).',
        )}
        {para(
          'If that godown has none of the item, completing the invoice is blocked even though other godowns hold stock. The error message names the godown it checked and lists where the stock actually is.',
        )}
        {para(
          '**Fix:** edit the invoice and change the **Godown** to the one holding the stock, or move stock with a **Stock Transfer** first.',
        )}
      </Stack>
    ),
  },
  {
    id: 'reserved-vs-on-hand',
    category: 'Stock & Godowns',
    question: 'What does "available" stock mean versus "on hand"?',
    keywords: ['reserved', 'allocated', 'draft invoice stock'],
    answer: (
      <Stack spacing={1.5}>
        {para(
          '**On hand** is the physical quantity in a godown. **Reserved** is the quantity already committed to open documents (for example unconfirmed sales orders or drafts). **Available = on hand − reserved** — that is the quantity you can still sell, and it is what stock checks and low-stock alerts use.',
        )}
      </Stack>
    ),
  },
];
