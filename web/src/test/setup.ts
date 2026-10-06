import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';

// Testing Library's default async wait is 1000 ms. Several page tests mount a whole editor (MUI, react-query,
// react-hook-form) and then `findBy*` / `waitFor` something on it; on a busy CI runner or a developer
// machine under load that mount takes longer than a second, and the test fails although the page is
// correct (seen in the full run: PurchaseOrderEditorPage.prefill and NewInvoicePage, both green in
// isolation). The wait only matters when an assertion would otherwise FAIL, so a longer ceiling slows
// nothing that passes and does not hide a real regression - an element that never appears still fails.
configure({ asyncUtilTimeout: 5000 });
