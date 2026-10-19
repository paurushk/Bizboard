import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // BB-000463: money lists must not use multi-page fetch; masters use fetchAllPagesMasters in resources.ts only.
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Identifier[name="fetchAllPages"]',
          message:
            'fetchAllPages is banned. Use list*Page / fetchMoneyListFirstPage for money docs, or fetchAllPagesMasters in resources.ts for masters.',
        },
      ],
    },
  },
  {
    files: ['src/api/legacy/**/*.ts'],
    rules: {
      '@typescript-eslint/no-unused-vars': 'off',
    },
  },
  {
    // Purchase review WP-8: destructive actions ask through the in-app dialog (confirmAction /
    // ConfirmDialog), never the browser popup. Tests may stub window.confirm.
    files: [
      'src/pages/purchases/**/*.{ts,tsx}',
      // Purchase-adjacent screens reviewed with the module (purchase review 2).
      'src/pages/imports/BillUploadPage.tsx',
      'src/pages/imports/bill/**/*.{ts,tsx}',
      'src/pages/reports/SupplierLedgerPage.tsx',
      'src/pages/reports/PurchaseReportPage.tsx',
      'src/pages/reports/Gstr2bPage.tsx',
      'src/pages/reports/MissingDocumentsPage.tsx',
      'src/pages/complaints/SupplierComplaintsPage.tsx',
      'src/pages/inventory/DemandForecastPage.tsx',
    ],
    ignores: ['**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Identifier[name="fetchAllPages"]',
          message:
            'fetchAllPages is banned. Use list*Page / fetchMoneyListFirstPage for money docs, or fetchAllPagesMasters in resources.ts for masters.',
        },
        {
          selector: "CallExpression[callee.object.name='window'][callee.property.name='confirm']",
          message: 'Use confirmAction() from @/utils/confirmBridge or <ConfirmDialog>, not window.confirm.',
        },
        {
          selector: "CallExpression[callee.name='confirm']",
          message: 'Use confirmAction() from @/utils/confirmBridge or <ConfirmDialog>, not confirm().',
        },
      ],
    },
  },
  {
    // ACT-21: invoice Share and POS Share must not grow a wa.me/{phone} or Cloud click-to-chat URL.
    // Reminder screens (collections, ledgers, UPI, GSTR-2B) stay outside this override.
    files: ['src/components/ShareInvoiceDialog.tsx', 'src/pages/pos/PosPage.tsx'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Identifier[name="fetchAllPages"]',
          message:
            'fetchAllPages is banned. Use list*Page / fetchMoneyListFirstPage for money docs, or fetchAllPagesMasters in resources.ts for masters.',
        },
        {
          selector: 'TemplateElement[value.raw=/wa\\.me\\/$/]',
          message:
            'Invoice and POS share must not target wa.me/{phone}. Use shareOnThisDevice (https://wa.me/?text=).',
        },
        {
          selector: 'Literal[value=/wa\\.me\\/\\d/]',
          message: 'Invoice and POS share must not target wa.me/{phone}. Use shareOnThisDevice.',
        },
        {
          selector: 'Literal[value=/api\\.whatsapp\\.com/]',
          message: 'Do not add api.whatsapp.com links on the invoice or POS share path.',
        },
        {
          selector: 'TemplateElement[value.raw=/api\\.whatsapp\\.com/]',
          message: 'Do not add api.whatsapp.com links on the invoice or POS share path.',
        },
      ],
    },
  },
  {
    // SET-10/SET-12: Settings screens ask through the in-app dialog and keep every visible string
    // in the i18n catalogue. The folder is clean (SET-24), so these are errors: a new raw English
    // string in visible text or in a label, placeholder, helper text, title, alt or aria-label fails lint.
    files: ['src/pages/settings/**/*.{ts,tsx}', 'src/components/settings/**/*.{ts,tsx}'],
    ignores: ['**/*.test.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: 'Identifier[name="fetchAllPages"]',
          message:
            'fetchAllPages is banned. Use list*Page / fetchMoneyListFirstPage for money docs, or fetchAllPagesMasters in resources.ts for masters.',
        },
        {
          selector: "CallExpression[callee.object.name='window'][callee.property.name='confirm']",
          message: 'Settings: use confirmAction() from @/utils/confirmBridge or <ConfirmDialog>, not window.confirm.',
        },
        {
          selector: "CallExpression[callee.name='confirm']",
          message: 'Settings: use confirmAction() from @/utils/confirmBridge or <ConfirmDialog>, not confirm().',
        },
        {
          selector: 'JSXText[value=/[A-Za-z]{3}/]',
          message: 'Settings: put visible text in the i18n catalogue (en.ts and hi.ts) and render it with t().',
        },
        {
          selector:
            'JSXAttribute[name.name=/^(label|placeholder|helperText|title|alt|aria-label)$/] > Literal[value=/[a-z]{3}/]',
          message: 'Settings: put this text in the i18n catalogue (en.ts and hi.ts) and render it with t().',
        },
      ],
    },
  },
);
