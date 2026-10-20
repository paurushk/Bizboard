/**
 * SET-20: what each Settings screen changes elsewhere in Bizboard. The screen frame shows these as
 * "Used by" chips, and the contract tests keep this list, the screen list and the backend twin
 * (`backend/core/settings_impact.py`) in step. Per-setting entries say which consumers one field reaches.
 */
export interface SettingImpact {
  key: string;
  consumers: readonly string[];
}

export const SCREEN_IMPACT: Readonly<Record<string, readonly string[]>> = {
  company: ['nav.sales', 'nav.purchases', 'impact.printedDocuments'],
  gst: ['nav.sales', 'nav.purchases', 'nav.gstr1', 'impact.einvoice'],
  'statutory-licences': ['impact.printedDocuments', 'nav.sales'],
  'bank-accounts': ['impact.printedDocuments', 'impact.upiQr', 'nav.receipts', 'nav.bankReconciliation'],
  'payment-gateway': ['nav.paymentLinks', 'nav.sales'],
  'money-in-rules': ['nav.receipts', 'nav.bankReconciliation', 'nav.sales', 'impact.reminders'],
  'price-lists': ['nav.customers', 'nav.sales', 'nav.pos'],
  'accounting-settings': ['nav.accounting', 'nav.sales', 'nav.purchases'],
  series: ['nav.sales', 'nav.purchases', 'impact.printedDocuments'],
  templates: ['impact.printedDocuments'],
  units: ['nav.products', 'nav.sales', 'nav.gstr1'],
  'item-settings': ['nav.products', 'nav.sales'],
  users: ['impact.signIn'],
  import: ['nav.products', 'nav.customers', 'nav.suppliers'],
  tally: ['nav.products', 'nav.customers', 'nav.suppliers'],
  backup: ['impact.yourData'],
  billing: ['impact.plan'],
  'ai-settings': ['impact.billScan', 'nav.purchases'],
  'pack-wizard': ['impact.menu'],
  telegram: ['impact.alerts'],
  'help-health': [],
  'counter-diagnostics': [],
};

export const SETTING_IMPACT: readonly SettingImpact[] = [
  { key: 'company.name', consumers: ['impact.printedDocuments'] },
  { key: 'company.address', consumers: ['impact.printedDocuments', 'nav.sales'] },
  { key: 'company.state', consumers: ['nav.sales', 'nav.purchases', 'nav.gstr1'] },
  { key: 'company.logo', consumers: ['impact.printedDocuments'] },
  { key: 'gst.registration_type', consumers: ['nav.sales', 'nav.gstr1'] },
  { key: 'gst.gstin', consumers: ['nav.sales', 'nav.gstr1', 'impact.einvoice', 'impact.printedDocuments'] },
  { key: 'gst.negative_stock_policy', consumers: ['nav.sales', 'nav.inventory'] },
  { key: 'gst.eway_threshold_amount', consumers: ['nav.sales'] },
  { key: 'licence.licence_number', consumers: ['impact.printedDocuments'] },
  { key: 'licence.valid_upto', consumers: ['nav.sales'] },
  { key: 'bank.print_on_invoices', consumers: ['impact.printedDocuments'] },
  { key: 'bank.upi_id', consumers: ['impact.upiQr'] },
  { key: 'bank.is_default', consumers: ['nav.receipts'] },
  { key: 'gateway.payment_gateway_credentials_encrypted', consumers: ['nav.paymentLinks'] },
  { key: 'gateway.payment_gateway_provider', consumers: ['nav.paymentLinks'] },
  { key: 'money_in.cash_269st_mode', consumers: ['nav.receipts'] },
  { key: 'money_in.dunning_enabled', consumers: ['impact.reminders'] },
  { key: 'money_in.require_payment_reference', consumers: ['nav.receipts'] },
  { key: 'price_list.is_active', consumers: ['nav.sales', 'nav.pos'] },
  { key: 'price_list.items', consumers: ['nav.sales', 'nav.pos'] },
  { key: 'accounting.accounting_enabled', consumers: ['nav.accounting'] },
  { key: 'series.prefix', consumers: ['nav.sales', 'nav.purchases', 'impact.printedDocuments'] },
  { key: 'series.next_number', consumers: ['nav.sales', 'nav.purchases'] },
  { key: 'templates.layout', consumers: ['impact.printedDocuments'] },
  { key: 'unit.uqc_code', consumers: ['nav.gstr1'] },
  { key: 'items.item_custom_field_defs', consumers: ['nav.products', 'nav.sales'] },
  { key: 'users.role', consumers: ['impact.signIn'] },
  { key: 'users.is_active', consumers: ['impact.signIn'] },
  { key: 'ai.opening_cash_balance', consumers: ['impact.cashFlow'] },
  { key: 'packs.flags', consumers: ['impact.menu'] },
];
