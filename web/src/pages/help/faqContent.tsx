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
  'Getting started',
  'Users & permissions',
  'GST & registration',
  'Sales invoices',
  'Quotations, orders & challans',
  'Customers',
  'Returns & notes',
  'Purchases & ITC',
  'Payments & banking',
  'Items & Units',
  'Stock & Godowns',
  'Batches, serials & expiry',
  'PDF, share & WhatsApp',
  'Reports & ledgers',
  'GSTR, e-Invoice & e-Way',
  'Accounting',
  'Import, Tally & backup',
  'POS & offline',
  'Subscription & billing',
  'Insights & AI',
  'Preview modules',
];

const para = (text: string): ReactNode => <HelpRichText text={text} />;

function faq(
  id: string,
  category: string,
  question: string,
  keywords: string[],
  paragraphs: string[],
): FaqItem {
  return {
    id,
    category,
    question,
    keywords,
    answer: (
      <Stack spacing={1.5}>
        {paragraphs.map((text) => (
          <HelpRichText key={text} text={text} />
        ))}
      </Stack>
    ),
  };
}

/** Original v0 entries — keep question/keyword copy byte-identical (faqV0Snapshot). */
const V0_FAQ_ITEMS: FaqItem[] = [
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

const MORE_FAQ: FaqItem[] = [
  faq(
    'what-is-bizboard',
    'Getting started',
    'What is Bizboard?',
    ['gst billing', 'erp', 'what is this', 'shop software', 'tagline'],
    [
      'Bizboard is GST billing for Indian shops, traders and small wholesalers. You make sales and purchase bills, keep stock by **t:inventory.godown**, take receipts and payments, and print or share invoices.',
      'GSTR worksheets, e-Invoice and full accounting books are optional extras. They are not a live GST portal and they do not file your return for you.',
    ],
  ),
  faq(
    'how-to-sign-up',
    'Getting started',
    'How do I create a company?',
    ['register', 'sign up', 'signup', 'create account', 'onboarding', 'wizard'],
    [
      'Open **Register**, enter the company name, your email, a password and the shop state. That creates the company and makes you the **Owner**.',
      'After login, Owners can run the setup wizard (tax, shop, payments, catalog, first bill) or skip it and use the dashboard checklist.',
    ],
  ),
  faq(
    'login-otp',
    'Getting started',
    'Can I log in with OTP instead of a password?',
    ['otp', 'sms', 'phone login', 'one time password', 'cooldown'],
    [
      'Email and password always work. Phone OTP appears only when OTP is turned on for this server and an SMS provider is configured.',
      'OTP has a 60-second cooldown and is limited to 5 sends per hour. If you do not see OTP, use your password or **Forgot password**.',
    ],
  ),
  faq(
    'forgot-password',
    'Getting started',
    'I forgot my password. What do I do?',
    ['reset password', 'forgot', 'invite link', 'cannot login'],
    [
      'Use **Forgot password** on the login screen. Enter the account email and follow the reset link.',
      'If you were invited and never set a password, open the invite link from your Owner instead of resetting.',
    ],
  ),
  faq(
    'hindi-ui',
    'Getting started',
    'Can I use Bizboard in Hindi?',
    ['hindi', 'language', 'हिंदी', 'i18n', 'english'],
    [
      'Yes. The app ships English and Hindi. Switch language from the language control in the app.',
      'Button names such as **t:common.complete** and **t:inventory.godown** stay the same in both languages so this Help page still matches the screen.',
    ],
  ),
  faq(
    'setup-wizard',
    'Getting started',
    'What does the setup wizard do?',
    ['onboarding', 'first bill', 'setup', 'checklist', 'sample products'],
    [
      'It is Owner-only. It walks tax → shop → payments → catalog → first bill. You can add a GSTIN, shop details, UPI or bank, optional sample products, and **t:common.complete** a first bill.',
      'If you skip it, the dashboard still shows an onboarding checklist.',
    ],
  ),

  faq(
    'roles',
    'Users & permissions',
    'What are the four roles?',
    ['owner', 'sales staff', 'accountant', 'viewer', 'role', 'permissions'],
    [
      '**Owner** runs the company: GST, users, billing and every action. **Sales staff** can bill sales and take receipts (purchases off by default). **Accountant** can enter purchases, payments and journals (sales off by default). **Viewer** can look, not create.',
      'The Owner can turn extra capabilities on or off per person in **t:nav.settings** → **t:nav.users**.',
    ],
  ),
  faq(
    'login-cant-do-this',
    'Users & permissions',
    'Why does the screen say my login cannot do this?',
    ['permission denied', '403', 'access denied', 'forbidden', 'cannot do this'],
    [
      'Your role or a capability flag does not include that action. Sales staff cannot manage GST or invite users. Accountants cannot create sales unless the Owner turns create-sales on. Viewers cannot change anything.',
      'Ask the Owner to open **t:nav.settings** → **t:nav.users** and grant the capability, or to do the action for you.',
    ],
  ),
  faq(
    'invite-teammate',
    'Users & permissions',
    'How do I invite a teammate?',
    ['invite', 'add user', 'staff', 'email invite', 'set password'],
    [
      'Only the Owner can invite. Open **t:nav.settings** → **t:nav.users**, enter their email, pick a role, and optionally set a password.',
      'If you skip the password, they get an invite link and set one at `/invite`. You cannot invite another Owner.',
    ],
  ),
  faq(
    'limited-access-home',
    'Users & permissions',
    'Why do I land on Limited access instead of the dashboard?',
    ['limited access', 'no menu', 'zero permission', 'sales staff home'],
    [
      'Sales staff with every create capability turned off have nowhere useful to work. The home page is a limited-access landing instead of KPIs they cannot see.',
      'Ask the Owner to grant create sales, create payments, or another capability so a real menu appears.',
    ],
  ),
  faq(
    'multi-company',
    'Users & permissions',
    'Can one login belong to more than one company?',
    ['switch company', 'tenant', 'multi company', 'branch', 'x-company-id'],
    [
      'Yes, with consent. Pick the company in the switcher so work stays in the right books.',
      'A **t:inventory.godown** is a stock location inside one company — not a separate legal branch. Extra GSTINs live under **t:nav.settings** → **t:nav.gst**.',
    ],
  ),
  faq(
    'viewer-reports',
    'Users & permissions',
    'Can a Viewer see financial reports?',
    ['viewer', 'reports permission', 'can view financial', 'least privilege'],
    [
      'Not by default. View financial reports is off for Viewers. The Owner can turn that capability on.',
      'Cancel, import, inventory manage and export are also off unless granted.',
    ],
  ),

  faq(
    'add-gstin',
    'GST & registration',
    'How do I add or change our GSTIN?',
    ['gstin', 'gstn', 'gst number', '15 character', 'company gstin'],
    [
      'A GSTIN is your 15-character GST number. Tax bills need it so the tax office can match the sale. Add it once in **t:nav.settings** → **t:nav.gst**.',
      'If you have more than one GSTIN, pick the right one on the bill before you press **t:common.complete**.',
    ],
  ),
  faq(
    'registration-type',
    'GST & registration',
    'Regular, Composition, or Unregistered — what should I pick?',
    ['composition', 'unregistered', 'regular gst', 'bill of supply', 'cmp-08'],
    [
      '**Regular** issues GST tax invoices (CGST+SGST or IGST) and uses GSTR-1 / GSTR-3B worksheets. **Composition** cannot issue regular GST or TAX invoices — use a bill of supply / non-GST invoice, and CMP-08 / GSTR-4 aids. **Unregistered** also cannot issue GST or TAX invoices.',
      'This is set at sign-up and in **t:nav.settings** → **t:nav.gst**. Only the Owner should change it.',
    ],
  ),
  faq(
    'unregistered-gst-invoice',
    'GST & registration',
    'Why can’t we make a GST invoice?',
    ['registration gate', 'composition invoice', 'unregistered cannot', 'tax invoice blocked'],
    [
      'The company registration type is **Unregistered** or **Composition**. Those types are blocked from completing GST or TAX invoices that carry CGST, SGST or IGST.',
      'Switch the invoice type to non-GST / retail, or ask the Owner to set **Regular** in **t:nav.settings** → **t:nav.gst** if you are actually registered.',
    ],
  ),
  faq(
    'place-of-supply',
    'GST & registration',
    'Why does Complete ask for place of supply?',
    ['pos', 'place of supply', 'state', 'blank party', 'walk-in', 'intra-state'],
    [
      'GST bills need the customer’s (or supplier’s) state so tax splits correctly. Set the party’s state or GSTIN.',
      'If the party is blank, the company can treat it as your local state (default on) or you must confirm a blank place of supply. Point of Sale walk-in bills show the same confirm.',
    ],
  ),
  faq(
    'cgst-vs-igst',
    'GST & registration',
    'When is CGST+SGST used versus IGST?',
    ['igst', 'cgst', 'sgst', 'inter state', 'intra state', 'sez', 'export', 'recompute tax'],
    [
      'Same state as your filing GSTIN → CGST + SGST. Different state → IGST. SEZ with payment and export with payment use IGST only. SEZ or export without payment must be zero GST.',
      'If recompute tax on complete is on and the split changes the total by more than ₹0.01, **t:common.complete** asks you to confirm the new total.',
    ],
  ),
  faq(
    'allowed-gst-rates',
    'GST & registration',
    'Which GST rates can I put on a line?',
    ['gst rate', '18%', '40%', 'invalid gst rate', 'slab', 'hsn rate'],
    [
      'Only the legal slabs: 0, 0.25, 3, 5, 12, 18, 28 and 40 percent. Half-rates or made-up numbers are rejected.',
      'Pick the rate that matches the item’s HSN, or fix HSN on the product.',
    ],
  ),
  faq(
    'tax-inclusive-price',
    'GST & registration',
    'Are prices tax-inclusive or exclusive?',
    ['inclusive', 'exclusive', 'price mode', 'tax in price', 'mrp'],
    [
      'The company has one price mode: exclusive or inclusive. Inclusive means the line price already contains GST and Bizboard backs out tax. Exclusive adds GST on top.',
      'You set this for the company, not per bill.',
    ],
  ),
  faq(
    'pan-udyam-verify',
    'GST & registration',
    'GSTIN / PAN / UDYAM verify failed. Can I still save?',
    ['pan', 'udyam', 'verify', 'checksum', 'soft fail'],
    [
      'Yes. PAN and UDYAM checks are hints: a failed verify never blocks save. GSTIN still has to pass format and checksum.',
      'Enter the number carefully. Verification is not a government approval.',
    ],
  ),
  faq(
    'godown-vs-branch-gstin',
    'GST & registration',
    'Is a Godown the same as a GST branch?',
    ['branch gstin', 'warehouse vs gstin', 'multi gstin', 'series'],
    [
      'No. A **t:inventory.godown** is a stock location. A branch GSTIN is a second 15-character GSTIN under **t:nav.settings** → **t:nav.gst**.',
      'Invoice numbers are keyed by GSTIN and the April–March year when any GSTIN exists. Moving stock between godowns does not change which GSTIN files the bill.',
    ],
  ),
  faq(
    'composition-returns',
    'GST & registration',
    'We are Composition. Why is GSTR-1 empty or blocked?',
    ['composition gstr1', 'cmp-08', 'gstr-4', 'composition dealer'],
    [
      'Composition dealers do not file regular GSTR-1 / GSTR-3B from this product. Use CMP-08 / GSTR-4 aids instead.',
      'Regular GSTR worksheets are blocked for composition companies on purpose.',
    ],
  ),

  faq(
    'cannot-complete-invoice',
    'Sales invoices',
    'Why is Complete greyed out or failing?',
    ['complete failed', 'cannot complete', 'greyed', 'blocked complete', 'invoice error'],
    [
      '**t:common.complete** needs at least one line, quantity greater than 0, a resolved place of supply, an allowed invoice type for your registration, stock in the bill’s **t:inventory.godown**, an active product and an unblocked customer.',
      'Credit limit, a closed period, missing company GSTIN (when you have more than one), unconfirmed sales reverse charge, or an after-tax discount on a B2B GST bill can also stop it. Read the error — it names the rule.',
    ],
  ),
  faq(
    'edit-completed-invoice',
    'Sales invoices',
    'Can I edit or delete a completed invoice?',
    ['edit invoice', 'delete bill', 'immutable', 'credit note instead', 'void'],
    [
      'No. A completed bill is frozen. Change it with a **t:nav.creditNotes** or **t:nav.debitNotes**, or **t:common.cancel** if nothing is allocated and you have cancel permission.',
      'Line-edit is blocked so history and GST worksheets stay meaningful.',
    ],
  ),
  faq(
    'cancel-invoice',
    'Sales invoices',
    'How do I cancel an invoice?',
    ['cancel bill', 'void invoice', 'unallocate', 'payment link cancel', 'can cancel documents'],
    [
      'Open the invoice → **t:common.cancel**. You need cancel permission, or be the Owner. If receipts are allocated, remove those allocations first.',
      'A completed sales return blocks cancel; clear draft returns first if those exist. Cancelling also cancels any open payment link on that bill.',
    ],
  ),
  faq(
    'invoice-types',
    'Sales invoices',
    'What is the difference between GST, TAX, RETAIL and NON_GST invoices?',
    ['retail invoice', 'tax invoice', 'bill of supply', 'non gst', 'invoice type'],
    [
      '**GST** and **TAX** are tax invoices (need Regular registration and place of supply). **RETAIL** is a counter / B2C style bill. **NON_GST** is a bill of supply / outside GST.',
      'Composition and Unregistered companies should not complete GST or TAX invoices.',
    ],
  ),
  faq(
    'b2b-after-tax-discount',
    'Sales invoices',
    'Why can’t I give an after-tax discount on a B2B GST bill?',
    ['after tax discount', 'invoice discount', 'b2b discount', 'before tax'],
    [
      'After-tax invoice discounts are blocked on B2B GST invoices. Use a before-tax discount on the lines, or issue a **t:nav.creditNotes** after the bill is completed.',
      'That keeps taxable value legal for e-Invoice and GSTR worksheets.',
    ],
  ),
  faq(
    'sales-rcm',
    'Sales invoices',
    'What is sales reverse charge and why must I confirm it?',
    ['rcm', 'reverse charge', 'confirm_sales_rcm', 'buyer pays gst'],
    [
      'Reverse charge means the buyer pays the GST, not you. If the bill is marked sales RCM, **t:common.complete** requires an explicit confirm so it is never applied by accident.',
      'Confirm on complete, or take RCM off the bill if it should be forward charge.',
    ],
  ),
  faq(
    'credit-limit-exceeded',
    'Sales invoices',
    'Complete says credit limit exceeded. What now?',
    ['credit limit', 'exposure', 'outstanding', 'cannot bill customer'],
    [
      'The customer’s open exposure plus this bill is over the limit set on the customer. Take a receipt and allocate it, ask the Owner to raise the limit, or bill a smaller amount.',
      'A zero or blank limit means no check.',
    ],
  ),
  faq(
    'invoice-number-when',
    'Sales invoices',
    'When does the invoice get a number?',
    ['invoice number', 'inv-00001', 'series', 'draft number', 'document number'],
    [
      'On **t:common.complete**, not on save-as-draft. Drafts have no legal number. Prefixes include INV, PUR, QTN, SRN, RCT, PAY and others.',
      'With any GSTIN on the company, the series is keyed by GSTIN and the April–March year (for example `INV-2627-…`).',
    ],
  ),
  faq(
    'number-restarted',
    'Sales invoices',
    'Why did invoice numbers restart or look different?',
    ['number reset', 'new series', 'financial year', 'gstin series', 'preview wrong number'],
    [
      'A new April–March GST year starts a new series. A second GSTIN has its own series. Drafts do not consume numbers.',
      'If preview showed `INV-00001` but Complete saved `INV-2627-…`, pick the GSTIN on the bill and complete again from a fresh preview.',
    ],
  ),
  faq(
    'closed-period-complete',
    'Sales invoices',
    'Why does Complete fail because of a closed period?',
    ['closed period', 'period lock', 'soft close', 'hard close', 'gst period'],
    [
      'A hard-closed GST or accounting period blocks new money documents. Soft-close of a GST period warns on Complete but still hard-blocks later money amends.',
      'Ask the Owner to open **t:nav.accountingPeriods** or the GST period lock, or post into an open month.',
    ],
  ),
  faq(
    'invoice-shortcuts',
    'Sales invoices',
    'What keyboard shortcuts work on a new invoice?',
    ['ctrl s', 'ctrl enter', 'f2', 'barcode', 'shortcut', 'hotkey'],
    [
      'Ctrl/Cmd+S saves a draft. Ctrl/Cmd+Enter completes. Ctrl/Cmd+Shift+L focuses product search. F2 is barcode.',
      'These are on the invoice editor, not on every screen.',
    ],
  ),
  faq(
    'recurring-invoices',
    'Sales invoices',
    'Do recurring invoices send themselves?',
    ['recurring', 'schedule', 'auto invoice', 'subscription bill', 'draft only'],
    [
      'No. A schedule only creates a draft invoice. Bizboard never auto-completes a recurring invoice.',
      'Open **t:nav.sales** → **t:nav.recurringInvoices**, then open the draft and press **t:common.complete** when you have checked stock, GSTIN and the customer.',
    ],
  ),
  faq(
    'sez-export-types',
    'Sales invoices',
    'How do I bill SEZ or export?',
    ['sez', 'export', 'sezwp', 'expwp', 'sezwop', 'zero gst', 'igst only'],
    [
      'Pick the supply type on the invoice. SEZ with payment (SEZWP) and export with payment (EXPWP) must be IGST only.',
      'SEZ or export without payment (SEZWOP / EXPWOP) must be zero GST. Do not put CGST+SGST on those bills.',
    ],
  ),
  faq(
    'hsn-warnings',
    'Sales invoices',
    'Complete warns about HSN but still works. Is that OK?',
    ['hsn warning', '6 digit', 'aato', 'additional charges', 'e-way warning'],
    [
      'Missing HSN, HSN shorter than 6 digits versus your AATO, and B2B additional charges without a taxable HSN are warnings, not hard blocks. Fix them before filing season.',
      'E-Way threshold without an e-Way is also a warning.',
    ],
  ),
  faq(
    'upload-sales-bill',
    'Sales invoices',
    'What does Upload Sales Bill do?',
    ['ocr', 'photo bill', 'scan invoice', 'ai extract', 'upload sales'],
    [
      'It is an assist: photo or PDF → a draft invoice for you to check. It does not invent GST rate or quantity.',
      'You still **t:common.complete** the draft. You need the import capability. Open **t:nav.sales** → **t:nav.uploadSalesBill**.',
    ],
  ),

  faq(
    'quotation-convert',
    'Quotations, orders & challans',
    'How do I turn a quotation into an invoice?',
    ['quote', 'convert quotation', 'estimate', 'blocked customer quote'],
    [
      'Open **t:nav.sales** → **t:nav.quotations**. Convert is allowed only from the right status. A blocked customer cannot convert.',
      'Conversion creates an invoice (or order). It does not auto-complete the invoice.',
    ],
  ),
  faq(
    'sales-order-reserve',
    'Quotations, orders & challans',
    'Does a sales order hold stock?',
    ['sales order', 'reserve', 'confirmed so', 'fefo', 'allocated stock'],
    [
      'Yes. Confirming a sales order reserves quantity. Available = on hand − reserved. Billing and low-stock use available.',
      'Cancel or invoice the order to release or consume the reserve. Batch items reserve FEFO lots (nearest expiry first).',
    ],
  ),
  faq(
    'delivery-challan',
    'Quotations, orders & challans',
    'When does a delivery challan move stock?',
    ['challan', 'dc', 'stock on delivery', 'convert challan', 'dispatch'],
    [
      'By default, stock moves when the invoice Completes. If the Owner turns on stock on delivery challan, completing the challan posts the sale movement instead.',
      'One challan per sales order. You can convert a challan to an invoice once. Cancel rules tighten if stock already posted. Open **t:nav.deliveryChallans**.',
    ],
  ),
  faq(
    'challan-eway-distance',
    'Quotations, orders & challans',
    'Why won’t e-Way generate on a delivery challan?',
    ['eway challan', 'transport distance', 'km', 'distance required'],
    [
      'Challan e-Way needs transport distance (km) filled in on the challan e-Way panel.',
      'Invoice e-Way uses the company’s e-Way settings and threshold under **t:nav.settings** → **t:nav.gst**.',
    ],
  ),

  faq(
    'blocked-customer',
    'Customers',
    'Why can’t I bill this customer?',
    ['blocked party', 'customer blocked', 'cannot create invoice', 'status blocked'],
    [
      'The party status is blocked. Blocked customers cannot get a new invoice or a converted quotation.',
      'Ask the Owner to open **t:nav.sales** → **t:nav.customers**, set status back to active, or pick another customer. This is a credit or compliance hold, not a software error.',
    ],
  ),
  faq(
    'customer-credit-limit',
    'Customers',
    'How do customer credit limits work?',
    ['credit limit', 'party limit', 'exposure', 'outstanding limit'],
    [
      'Set a limit greater than zero on the customer. **t:common.complete** is blocked when open exposure plus this invoice exceeds the limit.',
      'Exposure follows customer outstanding (bills minus credit notes plus debit notes minus allocated receipts). A zero or blank limit means no check.',
    ],
  ),
  faq(
    'price-lists',
    'Customers',
    'What is a price list?',
    ['rate card', 'price list', 'customer price', 'selling price'],
    [
      'A named rate card in **t:nav.settings** → **t:nav.priceLists**, then attached to a customer.',
      'Lines on a new invoice pick that selling price instead of the product default. Owner-managed.',
    ],
  ),
  faq(
    'duplicate-customer-gstin',
    'Customers',
    'Why can’t I save a customer with this GSTIN?',
    ['duplicate gstin', 'party gstin exists', 'unique gstin'],
    [
      'Another customer in this company already has that GSTIN. Duplicate party GSTINs are rejected.',
      'Search **t:nav.customers** for the existing party and reuse it, or fix the number.',
    ],
  ),
  faq(
    'walk-in-customer',
    'Customers',
    'How do I bill a walk-in with no GSTIN?',
    ['walk in', 'cash customer', 'blank party', 'counter sale', 'b2c'],
    [
      'Leave the party blank or use a walk-in customer. Place of supply follows assume-local-state for a blank party (default on), or you confirm a blank place of supply. That typically makes the bill intra-state.',
      'For a named B2B buyer, always put GSTIN and state.',
    ],
  ),

  faq(
    'credit-vs-cancel',
    'Returns & notes',
    'Should I cancel the invoice or issue a credit note?',
    ['credit note vs cancel', 'void vs cn', 'return vs cancel'],
    [
      '**t:common.cancel** voids a bill that should never have existed (wrong party, test bill) and needs no allocated receipts.',
      'A **t:nav.creditNotes** is the legal way to reduce a completed tax invoice (return, post-sale discount, deficiency, correction). Prefer credit notes once the bill is in the customer’s books or in GSTR worksheets.',
    ],
  ),
  faq(
    'credit-note-reasons',
    'Returns & notes',
    'Which credit-note reason should I pick?',
    ['sales return reason', 'post sale discount', 'deficiency', 'correction of invoice'],
    [
      'Use sales return, post-sale discount, deficiency in service, correction of invoice, or others.',
      'GST credit notes must link the original invoice. Reason codes matter for e-Invoice notes later. Open **t:nav.creditNotes**.',
    ],
  ),
  faq(
    'sales-return',
    'Returns & notes',
    'How do sales returns work?',
    ['sales return', 'srn', 'goods back', 'return against invoice'],
    [
      'Open **t:nav.sales** → **t:nav.salesReturns** against a completed sale. Completing the return brings stock back and adjusts the party.',
      'You cannot cancel the original invoice if a completed return already exists.',
    ],
  ),
  faq(
    'debit-notes',
    'Returns & notes',
    'When do I use a debit note?',
    ['debit note', 'under billed', 'extra charge', 'sdn'],
    [
      'A sales debit note increases what the customer owes after a completed invoice (extra charge, under-billing). Completed notes are not line-edited — reverse with the opposite note.',
      'Purchase debit and credit notes follow the same idea on the supplier side. Open **t:nav.debitNotes**.',
    ],
  ),
  faq(
    'cn-statutory-window',
    'Returns & notes',
    'Is there a last date to issue a GST credit note?',
    ['30 november', 'nov 30', 'section 34', 'credit note deadline', 'annual return'],
    [
      'GST law caps credit notes that change output tax at 30 November after the financial year (or annual return filing, whichever is earlier).',
      'Bizboard currently enforces period lock, not that statutory cutoff. Your CA should still watch 30 Nov. Do not treat a successful Complete as still legal forever.',
    ],
  ),

  faq(
    'purchase-no-grn',
    'Purchases & ITC',
    'Where is goods received (GRN)?',
    ['grn', 'goods receipt', 'inward', 'purchase complete stock'],
    [
      'There is no separate GRN. **t:common.complete** on a purchase bill posts stock and the supplier payable together.',
      'If goods arrive later than the bill, keep the bill as draft until you can complete both, or use opening stock / a stock adjustment for timing differences.',
    ],
  ),
  faq(
    'purchase-bill-blocked',
    'Purchases & ITC',
    'Why won’t the purchase bill Complete?',
    ['purchase complete', 'purchase blocked', 'supplier gstin', 'purchase error'],
    [
      'Same GST gates as sales: supplier state or GSTIN, registration type, closed period. Extra purchase rules: unregistered supplier needs reverse charge on, or confirm no RCM; foreign or import suppliers are not supported yet; duplicate supplier bill number needs confirm.',
      'Read the error on **t:nav.purchases**.',
    ],
  ),
  faq(
    'purchase-rcm',
    'Purchases & ITC',
    'Supplier has no GSTIN. What do I do?',
    ['unregistered supplier', 'purchase rcm', 'confirm no rcm', 'gta', 'section 9(3)'],
    [
      'Either turn reverse charge on for that bill, or explicitly confirm no RCM. Completing without one of those two is blocked.',
      'GTA-like lines (SAC 9965/9967 or “gta” in the name) show a Section 9(3) warning — still confirm deliberately.',
    ],
  ),
  faq(
    'foreign-purchase',
    'Purchases & ITC',
    'Can I enter an import purchase?',
    ['import', 'foreign supplier', 'overseas', 'bill of entry'],
    [
      'Not yet. Foreign supplier / import-of-goods is a hard block.',
      'Record the landed cost outside this flow or use a domestic supplier bill. Do not fake an Indian GSTIN to bypass the gate.',
    ],
  ),
  faq(
    'duplicate-supplier-bill',
    'Purchases & ITC',
    'It says this supplier bill number already exists.',
    ['duplicate bill', 'supplier invoice number', 'same bill no'],
    [
      'The same supplier + bill number was entered before. That is usually a duplicate paste.',
      'If it is truly a new bill (printer reused numbers), confirm the duplicate and continue. Otherwise open the existing purchase instead.',
    ],
  ),
  faq(
    'itc-unreviewed',
    'Purchases & ITC',
    'When can I claim ITC on a purchase?',
    ['itc', 'claimable', 'unreviewed', 'input tax', '2b match'],
    [
      'New purchases start as Unreviewed. Do not treat them as claimed ITC. Mark Claimable only after you have reviewed the bill.',
      'If GSTR-2B rows exist, Claimable also needs the 2B row matched to that purchase. Unreviewed ITC is not auto-claimed in GSTR-3B worksheets.',
    ],
  ),
  faq(
    'gstr3b-no-auto-accept',
    'Purchases & ITC',
    'Does GSTR-3B auto-claim my purchase GST?',
    ['gstr3b itc', 'table 4a', 'auto accept', 'ims'],
    [
      'No. Table 4A follows IMS / 2B review. There is no auto-accept. Books stay the source of truth.',
      'Marking everything Claimable without a 2B match is blocked when 2B data exists.',
    ],
  ),
  faq(
    'purchase-cn-link',
    'Purchases & ITC',
    'Why must a purchase credit note link a purchase invoice?',
    ['purchase credit note', 'pcn', 'link purchase', 'itc reversal'],
    [
      'GST purchase credit notes must point at the original purchase bill so ITC reversal and GSTR worksheets stay tied to a real document.',
      'Create the purchase first, **t:common.complete** it, then add the credit note under **t:nav.purchaseCreditNotes**.',
    ],
  ),
  faq(
    'upload-purchase-bill',
    'Purchases & ITC',
    'What does Upload Bill on purchases do?',
    ['ocr purchase', 'scan bill', 'upload bill', 'ai purchase'],
    [
      'Photo or PDF extract → a draft purchase for review. It will not invent GST rate or quantity.',
      'You still check HSN, GSTIN and **t:common.complete**. Needs import capability. Open **t:nav.purchases** → **t:nav.uploadBill**.',
    ],
  ),

  faq(
    'payment-wont-allocate',
    'Payments & banking',
    'Why won’t a receipt allocate to an invoice?',
    ['allocate', 'unapplied', 'allocation exceeds', 'receipt not sticking'],
    [
      'The receipt must be posted, the invoice completed (or returned), and the party must match. You cannot allocate more than the receipt’s unallocated amount or more than the invoice’s open outstanding.',
      'Fix the customer or supplier, lower the allocation, or take a new receipt. Open **t:nav.receipts**.',
    ],
  ),
  faq(
    'allocation-party-mismatch',
    'Payments & banking',
    'It says the party does not match.',
    ['party mismatch', 'wrong customer', 'allocation_party_mismatch'],
    [
      'You are allocating a customer receipt to another customer’s invoice (or a supplier payment to the wrong supplier).',
      'Open the correct party’s bills, or record the money on the right party first.',
    ],
  ),
  faq(
    'payment-links',
    'Payments & banking',
    'How do payment links work?',
    ['payment link', 'razorpay', 'pay page', 'share link', 'public pay'],
    [
      'Create a link on a completed invoice (**t:nav.payments** → **t:nav.paymentLinks**). Share WhatsApp or email. The buyer pays at the public pay page. Capture creates a receipt and allocates it.',
      'You cannot create a link on a draft. Cancelling a paid link is blocked. Cancelling the invoice cancels an open link.',
    ],
  ),
  faq(
    'gateway-after-cancel',
    'Payments & banking',
    'The customer paid a link after we cancelled the invoice. Where is the money?',
    ['captured pending books', 'paid after cancel', 'gateway hold', 'needs attention'],
    [
      'The capture is parked as paid, pending books and a **t:nav.attention** alert is raised. It is never silently dropped.',
      'Do not void a gateway receipt — refund in the gateway. Then the Owner decides whether to revive the bill or keep the money unapplied.',
    ],
  ),
  faq(
    'require-utr',
    'Payments & banking',
    'Why does UPI or Bank payment ask for a UTR?',
    ['utr', 'reference', 'upi reference', 'require payment reference'],
    [
      'If require payment reference is on, UPI and bank receipts need a UTR or reference. Cash does not.',
      'Turn the setting off only if the Owner wants cash-like UPI entries.',
    ],
  ),
  faq(
    'bank-recon-ambiguous',
    'Payments & banking',
    'Why didn’t bank reconciliation tick the match by itself?',
    ['reconciliation', 'bank statement', 'auto match', 'ambiguous'],
    [
      'Ambiguous suggestions are never auto-applied. Upload the statement (**t:nav.bankStatements**), preview, commit, then confirm matches in **t:nav.bankReconciliation**.',
      'Accounting bank recon (when books are on) clears GL bank lines the same way — still no silent auto-match.',
    ],
  ),
  faq(
    'cash-book-vs-insights',
    'Payments & banking',
    'Is Cash Book the same as Insights cashflow?',
    ['galla', 'daily cash', 'cashflow forecast', 'cash book'],
    [
      'No. **t:nav.cashBook** is actual receipts and payments. Insights cashflow is a forecast and is not tax or bank truth.',
      'Use Cash Book for the day’s drawer.',
    ],
  ),
  faq(
    'upi-qr',
    'Payments & banking',
    'Where does the UPI QR come from?',
    ['upi', 'qr', 'vpa', 'user@bank', 'payee'],
    [
      'From the company UPI VPA (user@bank format) on **t:nav.settings** → **t:nav.company**. Point of Sale and invoice screens can show a QR for that VPA.',
      'The QR does not by itself mark the invoice paid — still record a UPI receipt, or wait for a payment-link capture.',
    ],
  ),
  faq(
    'dunning',
    'Payments & banking',
    'Will Bizboard remind customers about overdue invoices?',
    ['dunning', 'overdue', 'reminder', 'whatsapp reminder', 'sms reminder', 'quiet hours'],
    [
      'Only if the Owner turns dunning on in **t:nav.settings** → **t:nav.company**. Channels are WhatsApp Cloud and/or SMS, with quiet hours and a max reminder count.',
      'Gateway-captured invoices are skipped. This is opt-in, not on by default.',
    ],
  ),
  faq(
    'payment-modes',
    'Payments & banking',
    'Which payment modes can I record?',
    ['cash', 'upi', 'bank', 'card', 'credit', 'razorpay', 'cashfree', 'payu'],
    [
      'Cash, UPI, Bank, Card, and Credit (bill now, pay later). Credit invoices show in receivables until receipts are allocated.',
      'Payment-link captures follow the configured gateway (Razorpay primary; Cashfree or PayU when that option is on).',
    ],
  ),
  faq(
    'gateway-refund-not-void',
    'Payments & banking',
    'Can I delete a Razorpay receipt?',
    ['void gateway', 'refund', 'razorpay receipt', 'delete payment'],
    [
      'No. Gateway receipts are refunded, not voided, so the audit trail matches the payment provider.',
      'Use the gateway refund flow, then the books follow.',
    ],
  ),

  faq(
    'batch-xor-serial',
    'Items & Units',
    'Can an item track both batch and serial numbers?',
    ['batch', 'serial', 'track_batch', 'track_serial', 'xor'],
    [
      'No. Track batch and track serial are mutually exclusive. Pick one on the product.',
      'Opening stock and issues then require that batch or those serials.',
    ],
  ),
  faq(
    'inactive-product',
    'Items & Units',
    'Why can’t I add this item to a bill?',
    ['inactive product', 'stopped sku', 'cannot sell item', 'status inactive'],
    [
      'Inactive products cannot go on a new invoice. That stops old SKUs being sold by mistake.',
      'Ask the Owner to open **t:nav.products**, set status Active, then add the line again. If the error is stock, see the godown / available answers instead.',
    ],
  ),
  faq(
    'delete-product',
    'Items & Units',
    'Can I delete a product?',
    ['delete item', 'soft delete', 'inactive instead', 'remove sku'],
    [
      'If it was never used, yes. If invoices or stock movements reference it, delete becomes Inactive instead so history stays.',
      'You cannot sell inactive items until you reactivate.',
    ],
  ),
  faq(
    'duplicate-barcode',
    'Items & Units',
    'Why is this barcode rejected?',
    ['barcode', 'ean', 'duplicate barcode', 'sku unique'],
    [
      'Another product already has that barcode in this company. Barcodes must be unique.',
      'Use a different code or open the existing SKU in **t:nav.products**.',
    ],
  ),
  faq(
    'service-item-stock',
    'Items & Units',
    'Do service items affect stock?',
    ['service', 'non stock', 'sac', 'no stock movement'],
    [
      'Non-stock / service items do not post stock movements. You can still bill them with HSN or SAC and GST.',
      'Do not expect **t:nav.currentStock** to move.',
    ],
  ),
  faq(
    'item-custom-fields',
    'Items & Units',
    'How do extra item fields work?',
    ['custom fields', 'item settings', 'extra attributes'],
    [
      'The Owner defines them in **t:nav.settings** → **t:nav.itemSettings** (text or list, unique keys, a max active count). They show on the product form.',
      'They are shop labels — they do not change GST or stock math.',
    ],
  ),
  faq(
    'units-master',
    'Items & Units',
    'Where do I add a new unit like DOZEN?',
    ['uom', 'units settings', 'dozen', 'add unit'],
    [
      '**t:nav.settings** → **t:nav.units**. Add the unit, then pick it as base or alternate on the product.',
      'Prefer standard codes (PCS, KG) so imports match the dropdown.',
    ],
  ),

  faq(
    'negative-stock-policy',
    'Stock & Godowns',
    'Can we bill when stock is zero?',
    ['negative stock', 'block', 'warn', 'out of stock billing', 'allow negative'],
    [
      'That is Out-of-stock billing policy under **t:nav.settings** → **t:nav.gst**: Block (default) refuses Complete; Warn allows negative stock and shows a warning.',
      'Only the Owner should switch this. Negative stock makes valuation and GSTR quantity messy — prefer a transfer or purchase Complete first.',
    ],
  ),
  faq(
    'default-godown-delete',
    'Stock & Godowns',
    'Why can’t I delete or deactivate this godown?',
    ['delete warehouse', 'default godown', 'deactivate godown', 'godown has stock'],
    [
      'The default godown, or any godown that still has stock or movement history, cannot be removed that way. Transfer stock out, then deactivate.',
      'Inactive godowns cannot receive stock. Manage them under **t:nav.warehouses**.',
    ],
  ),
  faq(
    'stock-transfer',
    'Stock & Godowns',
    'How do I move stock between godowns?',
    ['transfer', 'move stock', 'godown to godown'],
    [
      '**t:nav.inventory** → **t:nav.stockTransfers**. Source and destination must differ. Draft → Complete.',
      'This is the fix when **t:nav.products** shows stock but the invoice godown is empty.',
    ],
  ),
  faq(
    'stock-count',
    'Stock & Godowns',
    'How do physical stock counts work?',
    ['stock count', 'physical count', 'variance', 'conflict 409', 'adjustment'],
    [
      '**t:nav.inventory** → **t:nav.stockCounts**. You enter counted quantity; Complete posts an adjustment.',
      'If someone else changed stock while you counted, you get a conflict and must recount — the app will not silently overwrite.',
    ],
  ),
  faq(
    'opening-stock-once',
    'Stock & Godowns',
    'Can I enter opening stock twice for the same item?',
    ['opening stock', 'duplicate opening', 'import opening'],
    [
      'Opening stock is once per warehouse + product + batch. Use a **t:nav.stockAdjustment** for later corrections, or import opening stock only on empty balances.',
      'Duplicate opening is rejected.',
    ],
  ),
  faq(
    'stock-valuation',
    'Stock & Godowns',
    'How is stock valued — FIFO or average?',
    ['fifo', 'wavg', 'weighted average', 'cogs', 'valuation'],
    [
      'Default is weighted average. FIFO can be turned on. Turning on valuation by business date can restate COGS — take a backup first.',
      'FIFO cost of goods is still incomplete in places; many reports use blended cost. Treat **t:nav.stockValuation** as a books aid, not a costing-engine guarantee.',
    ],
  ),
  faq(
    'low-stock',
    'Stock & Godowns',
    'Low stock looks wrong compared to Products.',
    ['reorder', 'low stock', 'available vs products', 'reserved low'],
    [
      '**t:nav.lowStock** uses available (after reserves). The company-wide available on **t:nav.products** can look healthier.',
      'Confirmed sales orders reserve quantity and can push an item onto Low stock while on hand still looks fine.',
    ],
  ),

  faq(
    'fefo-batch',
    'Batches, serials & expiry',
    'Which batch is picked when I don’t choose one?',
    ['fefo', 'expiry first', 'lot allocation', 'batch pick'],
    [
      'For batch-tracked items, **t:common.complete** allocates FEFO — nearest expiry first — unless you pick a batch on the line.',
      'Sales orders reserve the same way. You can still force a batch on the line when you must.',
    ],
  ),
  faq(
    'expired-batch-block',
    'Batches, serials & expiry',
    'Why can’t I sell this batch?',
    ['expired', 'block expired stock', 'past expiry', 'write off'],
    [
      'Block expired stock is on by default. Lots past expiry cannot be issued. Write off from **t:nav.expiryAlerts** or turn the policy off (Owner — usually a bad idea).',
      'Manufacturing work orders follow the same batch / FEFO rules when that module is on.',
    ],
  ),
  faq(
    'expiry-alerts',
    'Batches, serials & expiry',
    'What does Expiry Alerts do?',
    ['near expiry', 'writeoff', 'lot alert'],
    [
      '**t:nav.inventory** → **t:nav.expiryAlerts** lists lots nearing expiry so you can sell, transfer or write off.',
      'It is an operations queue, not an automatic stock adjustment until you act.',
    ],
  ),
  faq(
    'serial-numbers',
    'Batches, serials & expiry',
    'How do serial numbers work?',
    ['imei', 'serial register', 'track serial'],
    [
      'Turn track serial on the product (not batch). Opening and issue must list serials. **t:nav.inventory** → **t:nav.serials** is the register.',
      'You cannot mix batch and serial on one SKU.',
    ],
  ),

  faq(
    'pdf-or-share-unavailable',
    'PDF, share & WhatsApp',
    'Why can’t I download PDF or share this invoice?',
    ['pdf', 'share', 'draft pdf', 'generating', 'queued', 'whatsapp grey'],
    [
      'Only completed (or returned) invoices can PDF or share. Drafts are blocked. Wait until **t:common.complete** succeeds, then open the invoice in **t:nav.salesHistory**.',
      'PDF is built in the background: queued → ready. If you download too soon you get “PDF is generating, retry shortly”. Failed PDFs can be regenerated.',
    ],
  ),
  faq(
    'pdf-original-duplicate',
    'PDF, share & WhatsApp',
    'What is Original vs Duplicate on the PDF?',
    ['original', 'duplicate', 'rule 46', 'thermal', '58mm', '80mm'],
    [
      'Tax invoices support Original and Duplicate copies. Point of Sale can also print a thermal 58/80 mm slip when the PDF is ready.',
      'Purchase bills follow purchase-bill layout, not a sales tax invoice.',
    ],
  ),
  faq(
    'whatsapp-not-delivered',
    'PDF, share & WhatsApp',
    'I clicked WhatsApp. Did the customer get the invoice?',
    ['whatsapp', 'wa.me', 'cloud api', 'not delivered', 'opt in'],
    [
      'Not necessarily. If WhatsApp Cloud is not connected (or the customer has not opted in), Bizboard opens a chat link. That message is not delivered by Bizboard — you still send it in WhatsApp.',
      'Cloud send exists only when the Owner configured WhatsApp connection and templates are approved.',
    ],
  ),
  faq(
    'email-share-smtp',
    'PDF, share & WhatsApp',
    'Share by email never arrives.',
    ['smtp', 'email failed', 'mail not received', 'notification failed'],
    [
      'Share needs the customer’s email. If email is not really configured for this server, the notification is marked failed (SMTP) rather than pretending it was sent.',
      'Ask the Owner or whoever runs the server to set a real mail path. Check the share status on the invoice; do not assume Gmail received it.',
    ],
  ),
  faq(
    'share-needs-phone-email',
    'PDF, share & WhatsApp',
    'Share asks for phone or email.',
    ['mobile', 'customer email', 'recipient', 'share invoice'],
    [
      'WhatsApp needs a customer mobile; email needs an email on the customer (or you type a recipient).',
      'Add it on **t:nav.customers**, then share again. Payment-link share uses the same channels.',
    ],
  ),

  faq(
    'ledgers-derived',
    'Reports & ledgers',
    'Where is the customer ledger stored?',
    ['customer ledger', 'supplier ledger', 'derived', 'no ledger table'],
    [
      'It is not a separate table you type into. **t:nav.customerLedger** and **t:nav.supplierLedger** are built from completed documents plus allocations.',
      'That is why a missing allocation makes outstanding look unpaid. When accounting books are on and outstanding basis is GL, receivables can follow GL accounts instead of document math.',
    ],
  ),
  faq(
    'outstanding-mismatch',
    'Reports & ledgers',
    'Receivables don’t match the sum of unpaid invoices.',
    ['outstanding', 'receivables', 'unallocated', 'advances', 'tcs'],
    [
      'Outstanding is grand total − credit notes + debit notes − allocations (and TCS if not folded in). Unallocated receipts sit as advances.',
      'Books-on plus GL outstanding can differ from a simple invoice list. Open the party ledger and check allocations before changing invoices.',
    ],
  ),
  faq(
    'dashboard-kpis',
    'Reports & ledgers',
    'What does the dashboard show?',
    ['today sales', 'aging', 'kpis', 'needs attention', 'home'],
    [
      'Today’s sales, this month’s sales, purchases this month, low stock, customer outstanding, supplier payables, receivables aging and recent documents. Needs view-financial-reports.',
      '**t:nav.attention** is a separate ops queue (gateway holds, GST issues and similar).',
    ],
  ),
  faq(
    'ca-needs',
    'Reports & ledgers',
    'What is “What my CA needs”?',
    ['ca pack', 'missing bills', 'chartered accountant', 'ims missing'],
    [
      'A client-toned view of missing bills versus IMS/2B — the same missing-documents report with friendlier copy. You can request a bill on WhatsApp or attach a photo into the import queue.',
      'It does not file GST for you. Open **t:nav.caNeeds**.',
    ],
  ),
  faq(
    'statutory-events',
    'Reports & ledgers',
    'What is the Statutory events report?',
    ['due dates', 'gst calendar', 'compliance dates'],
    [
      'A list of GST and compliance dates for the company. It is a reminder aid, not a filing confirmation from the GST portal.',
      'Open **t:nav.statutoryEvents**.',
    ],
  ),
  faq(
    'who-can-see-reports',
    'Reports & ledgers',
    'Who can open Reports?',
    ['reports permission', 'sales staff reports', 'access denied reports'],
    [
      'Users with view financial reports (Owner and Accountant by default). Sales staff and Viewers do not see the **t:nav.reports** section unless the Owner grants the capability.',
      'That avoids a menu click that only shows Access denied.',
    ],
  ),

  faq(
    'gstr-not-filing',
    'GSTR, e-Invoice & e-Way',
    'Does Bizboard file GSTR-1 or GSTR-3B on the GST portal?',
    ['file gstr', 'gstn', 'offline tool', 'not a filing engine', 'json'],
    [
      'No. **t:nav.gstr1**, **t:nav.gstr3b**, GSTR-9 and **t:nav.gstr2b** are offline worksheets and optional JSON for the government offline tool. They are not a filing engine.',
      'You or your CA still file on the GST portal. GSTR-6/7/8 screens are stubs with the same honesty.',
    ],
  ),
  faq(
    'gstr-2b-ims',
    'GSTR, e-Invoice & e-Way',
    'How do GSTR-2B and IMS work here?',
    ['ims', 'accept reject', '2b ingest', 'park', 'deemed accept'],
    [
      'Ingest 2B/IMS rows, then Accept, Reject (remark required) or Park. Do not auto-claim. Books remain the source of truth.',
      'Soft-closing a GST period can deemed-accept remaining IMS — Owner only. Open **t:nav.gstr2b**.',
    ],
  ),
  faq(
    'gstr-multi-gstin',
    'GSTR, e-Invoice & e-Way',
    'GSTR-1 looks empty for one of our GSTINs.',
    ['wrong gstin report', 'multi gstin gstr', 'filing gstin'],
    [
      'Companies with more than one GSTIN must pick the filing GSTIN on the report. Each GSTIN has its own worksheet.',
      'Bills completed under another GSTIN will not appear. Pick the GSTIN at the top of **t:nav.gstr1** / **t:nav.gstr3b**.',
    ],
  ),
  faq(
    'b2cl-threshold',
    'GSTR, e-Invoice & e-Way',
    'What is the B2CL threshold?',
    ['b2cl', '1 lakh', '2.5 lakh', 'large b2c', 'inter state unregistered'],
    [
      'From 1 August 2024 the B2CL (large unregistered inter-state) threshold in worksheets is ₹1 lakh (it used to be ₹2.5 lakh).',
      'Bills above that go to the B2CL bucket in GSTR-1 aids.',
    ],
  ),
  faq(
    'einvoice-live',
    'GSTR, e-Invoice & e-Way',
    'Is e-Invoice / e-Way live on NIC?',
    ['gsp', 'sandbox', 'irp', 'nic', 'live einvoice', 'certified'],
    [
      'Live NIC is fail-closed until the GSP is certified and live HTTP is enabled. Pilots use sandbox or preview. Empty live credentials fail; placeholder secrets are rejected.',
      'Do not promise customers that IRN is filed until live GSP is actually on for this company. Toggles live under **t:nav.settings** → **t:nav.gst**.',
    ],
  ),
  faq(
    'irn-cancel-24h',
    'GSTR, e-Invoice & e-Way',
    'How long can I cancel an IRN?',
    ['irn cancel', '24 hours', 'cnl1', 'cnl2', 'ack'],
    [
      'Cancel within 24 hours of acknowledgement, with reason codes CNL1–4 plus remarks. e-Invoice and e-Way actions are Owner-only and audited.',
      'After 24 hours, use a **t:nav.creditNotes**, not IRN cancel.',
    ],
  ),
  faq(
    'eway-threshold',
    'GSTR, e-Invoice & e-Way',
    'When is e-Way suggested?',
    ['e-way', '50000', '50,000', 'aato', '5 crore', 'einvoice threshold'],
    [
      'Company default e-Way threshold is ₹50,000 under **t:nav.settings** → **t:nav.gst**. Completing a bill over that without e-Way can warn.',
      'The AATO e-Invoice alert default is ₹5 crore. E-Invoice and e-Way toggles live on the same GST settings page.',
    ],
  ),
  faq(
    'gstr9-honesty',
    'GSTR, e-Invoice & e-Way',
    'Is GSTR-9 a filing pack?',
    ['gstr-9', 'annual return', 'tables 6-8', 'worksheet'],
    [
      'No. **t:nav.gstr9** is an outward FY books worksheet, not a filing pack.',
      'Your CA still prepares the annual return.',
    ],
  ),
  faq(
    'tds-tcs-aids',
    'GSTR, e-Invoice & e-Way',
    'Can I upload 26Q or 27EQ from Bizboard?',
    ['tds', 'tcs', '26q', '27eq', 'income tax portal'],
    [
      'No. **t:nav.tdsTcs** screens are filing aids, not live Income-tax portal upload.',
      'Use them to review collections, then file where the government requires.',
    ],
  ),

  faq(
    'books-journal-blocked',
    'Accounting',
    'Why can’t I post a journal?',
    ['journal', 'books off', 'accounting enabled', 'must balance', 'closed period'],
    [
      'Accounting is off by default. The Owner enables books in **t:nav.settings** → **t:nav.accounting**. You also need post-journals permission.',
      'Journals must balance. You cannot post into a hard-closed accounting period. System chart-of-accounts rows are not editable or deletable. Open **t:nav.journals**.',
    ],
  ),
  faq(
    'docs-source-of-truth',
    'Accounting',
    'If books are on, what is the source of truth — GL or invoices?',
    ['source of truth', 'gl vs documents', 'overlay'],
    [
      'Completed documents remain the source of truth. The general ledger is a books overlay.',
      'Party ledgers can follow documents plus allocations, or GL receivables when outstanding basis is set to GL-when-books.',
    ],
  ),
  faq(
    'journal-immutable',
    'Accounting',
    'Can I edit a posted journal?',
    ['contra', 'reverse journal', 'posted lines'],
    [
      'Posted lines are immutable. Reverse with a contra (opposite) journal.',
      'That is the same idea as credit notes on invoices.',
    ],
  ),
  faq(
    'soft-vs-hard-close',
    'Accounting',
    'What is soft close versus hard close?',
    ['soft close', 'hard close', 'period close', 'lock books'],
    [
      'Soft-close warns (GST Complete into a soft-closed GST period is warn-only) but later money amends are hard-blocked.',
      'Hard-close blocks new postings. The Owner manages **t:nav.accounting** → **t:nav.accountingPeriods**.',
    ],
  ),
  faq(
    'fy-close',
    'Accounting',
    'What does financial-year close do?',
    ['fy close', 'retained earnings', '3100', 'april', 'p&l zero'],
    [
      'FY close posts income and expense to retained earnings so profit and loss zeros for the next year.',
      'Books FY start month defaults to April and can differ from the GST series year (always April). Run only when the Owner is ready; it is not GST filing.',
    ],
  ),
  faq(
    'fixed-assets',
    'Accounting',
    'How are fixed assets depreciated?',
    ['slm', 'depreciation', 'asset register', 'wdv'],
    [
      '**t:nav.accounting** → **t:nav.fixedAssets** uses straight-line (SLM) depreciation when books are on.',
      'This is a books aid for small shops, not a full asset register for tax depreciation under the Income-tax Act — confirm with your CA.',
    ],
  ),
  faq(
    'coa-seeded',
    'Accounting',
    'Where does the chart of accounts come from?',
    ['coa', 'chart of accounts', 'system accounts', 'indian sme'],
    [
      'Enabling books seeds an Indian SME chart (including input/output CGST, SGST, IGST, reverse-charge payables and advances). System accounts cannot be deleted.',
      'Add extra accounts under the same company. Open **t:nav.chartOfAccounts**.',
    ],
  ),

  faq(
    'import-row-errors',
    'Import, Tally & backup',
    'My Excel import shows red rows and nothing saved.',
    ['import', 'excel', 'invalid rows', 'tally rows', 'commit blocked'],
    [
      'Any invalid row blocks the entire commit — nothing partial is written. Fix every red row (GSTIN, HSN, units, quantity) and import again.',
      'Types: Products, Customers, Suppliers, Opening stock. Needs import capability. Open **t:nav.settings** → **t:nav.importData**.',
    ],
  ),
  faq(
    'tally-not-sync',
    'Import, Tally & backup',
    'Does Tally stay in sync with Bizboard?',
    ['tally', 'live sync', 'migration', 'xml', 'one shot'],
    [
      'No. **t:nav.settings** → **t:nav.tallyMigration** is a one-shot upload / preview / commit and optional export dump. It is not bidirectional live sync.',
      'After go-live, pick one system as daily books.',
    ],
  ),
  faq(
    'backup-export',
    'Import, Tally & backup',
    'How do I take a backup?',
    ['backup', 'export', 'restore', 'encrypted'],
    [
      'The Owner (export capability) uses **t:nav.settings** → **t:nav.backupExport** for an encrypted company export.',
      'Restore is sandbox-oriented — not a casual undo.',
    ],
  ),
  faq(
    'opening-stock-import',
    'Import, Tally & backup',
    'How should I import opening stock?',
    ['opening stock import', 'excel opening', 'godown opening'],
    [
      'Use the Opening stock import after godowns and products exist. One opening per warehouse + product + batch, and company-wide vs godown still applies after import.',
      'Bad rows fail the whole file.',
    ],
  ),

  faq(
    'pos-what',
    'POS & offline',
    'What does Point of Sale do?',
    ['pos', 'counter', 'thermal', 'cash upi', 'barcode f2'],
    [
      'A counter flow: pick items, take cash or UPI, complete a retail invoice, record the receipt, and print thermal PDF when ready. It is a simple checkout, not a full restaurant POS.',
      'Walk-in / blank place-of-supply confirms still apply. Needs Point of Sale enabled and create-sales. Open **t:nav.pos**.',
    ],
  ),
  faq(
    'offline-outbox-stuck',
    'POS & offline',
    'Offline drafts are not syncing.',
    ['offline', 'outbox', 'pwa', 'queue', 'sync'],
    [
      'Open **t:offlineOutbox.title** on that same device. Drafts queue locally while the network is down, then sync when you are online.',
      'If a row is stuck, read the error (often the same Complete gates: stock, GSTIN, blocked customer). Sign-out wipes the device queue.',
    ],
  ),
  faq(
    'offline-plaintext',
    'POS & offline',
    'Are offline drafts encrypted on the phone?',
    ['unencrypted', 'plaintext', 'device storage', 'security'],
    [
      'No. The offline outbox stores drafts in plaintext on the device. Do not leave a logged-in counter unattended. Sign-out clears it.',
      'This is a browser / PWA shell, not a hardened offline database.',
    ],
  ),
  faq(
    'android-not-store-app',
    'POS & offline',
    'Is there a Play Store Android app?',
    ['android', 'play store', 'capacitor', 'mobile app', 'webview'],
    [
      'The Android wrapper is the same web app in a WebView — not a separate store product with its own features.',
      'Use the PWA in the browser or the wrapped WebView if you ship it. Help, roles and GST rules are the web app’s.',
    ],
  ),

  faq(
    'trial-ended-readonly',
    'Subscription & billing',
    'Everything is read-only after the trial.',
    ['trial', 'subscription', 'readonly', 'renew', 'paused'],
    [
      'When the trial ends or the subscription is paused, the workspace is read-only. The Owner renews in **t:nav.settings** → **t:nav.billing**.',
      'Staff should send this page to the Owner — they cannot pay from a Viewer login.',
    ],
  ),

  faq(
    'insights-not-tax',
    'Insights & AI',
    'Can I file GST from Insights or the assistant?',
    ['ai', 'assistant', 'insights', 'forecast', 'not tax advice'],
    [
      'No. **t:nav.insights** (hub, health, cashflow, alerts, assistant) are assistive figures and forecasts — not tax advice and not the GST portal.',
      'They appear only when AI is enabled for the product and the company, plus the user’s AI capabilities.',
    ],
  ),
  faq(
    'ai-settings',
    'Insights & AI',
    'Where do I turn AI features off?',
    ['disable ai', 'digest', 'daily email', 'cashflow baseline'],
    [
      'Owner: **t:nav.settings** → **t:nav.aiSettings**. Toggles cover features, digests, daily email and cashflow baseline.',
      'Turning company AI off hides Insights even if the server flag is on.',
    ],
  ),

  faq(
    'manufacturing-preview',
    'Preview modules',
    'Are BOMs and work orders a full manufacturing ERP?',
    ['bom', 'work order', 'manufacturing', 'mes', 'preview'],
    [
      'Only when manufacturing is on, and even then it is a preview: bill of materials plus work order (draft → release on an active BOM → complete or cancel) with FEFO or batch on issue.',
      'Do not treat it as a factory MES. It is Owner-gated in the menu. Open **t:nav.manufacturing**.',
    ],
  ),
  faq(
    'payroll-immutable',
    'Preview modules',
    'Can I edit a completed pay run?',
    ['payroll', 'pay run', 'employees', 'immutable payroll'],
    [
      'No. Completed pay runs are immutable. Correct with a new run if the module is enabled.',
      '**t:nav.employees** and **t:nav.payRuns** are Owner-gated.',
    ],
  ),
  faq(
    'crm-preview',
    'Preview modules',
    'Is CRM (leads / opportunities) ready for a sales team?',
    ['crm', 'leads', 'opportunities', 'pipeline'],
    [
      'It is a flagged preview (leads, opportunities), Owner-gated. Billing, stock and GST do not depend on it.',
      'Treat it as optional. **t:nav.customers** under Sales is the system of record for people you bill.',
    ],
  ),
];

export const FAQ_ITEMS: FaqItem[] = [...V0_FAQ_ITEMS, ...MORE_FAQ];
