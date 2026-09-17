import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * Purchase inbound stock cannot leave batch blank for FEFO (that is a sales
 * outbound rule). If this page reuses sales FEFO / "optional" copy, Complete
 * looks allowed while the gate still blocks it.
 */
describe('NewPurchasePage batch copy contract', () => {
  const src = readFileSync(resolve(__dirname, 'NewPurchasePage.tsx'), 'utf8');

  it('does not reuse sales FEFO / optional batch copy', () => {
    expect(src).not.toContain("billing.fefoBatch");
    expect(src).not.toContain("billing.newBatchOptional");
  });

  it('uses purchase-required batch copy and names the complete blocker', () => {
    expect(src).toContain("billing.purchaseBatchPlaceholder");
    expect(src).toContain("billing.purchaseBatchHint");
    expect(src).toContain("billing.purchaseNewBatch");
    expect(src).toContain("firstCompleteDisabledReason");
    expect(src).toContain("missingBatchName");
  });
});
