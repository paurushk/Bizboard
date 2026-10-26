import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';
import { loadContextHelpCatalog } from '@/contextHelp/catalogLoader';
import { registerLocale } from '@/i18n';
import type { MessageTree } from '@/i18n/en';
import { hi } from '@/i18n/hi';

// Testing Library's default async wait is 1000 ms. Several page tests mount a whole editor (MUI, react-query,
// react-hook-form) and then `findBy*` / `waitFor` something on it; on a busy CI runner or a developer
// machine under load that mount takes longer than a second, and the test fails although the page is
// correct (seen in the full run: PurchaseOrderEditorPage.prefill and NewInvoicePage, both green in
// isolation). The wait only matters when an assertion would otherwise FAIL, so a longer ceiling slows
// nothing that passes and does not hide a real regression - an element that never appears still fails.
configure({ asyncUtilTimeout: 5000 });

// The app fetches the Hindi catalogue on demand (src/i18n/index.ts); tests switch locale
// synchronously, so register it up front.
registerLocale('hi', hi as unknown as MessageTree);

// The page-help catalogue is fetched on demand in the app; load it once so the `?` button is there
// on first render in tests.
await loadContextHelpCatalog();
