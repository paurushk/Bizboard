import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { t } from '@/i18n';
import { renderRoutes } from '@/test/careHarness';

const state = vi.hoisted(() => ({
  role: 'OWNER',
  flags: {} as Record<string, boolean>,
  recipe: null as unknown,
  error: false,
}));

vi.mock('@/auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, companyId: 7, role: state.role } }) }));
vi.mock('@/hooks/useSubscriptionGate', () => ({ useSubscriptionGate: () => ({ writesBlocked: false }) }));
vi.mock('@/config/featureFlags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/config/featureFlags')>();
  return { ...actual, isRuntimeFlagEnabled: (key: string) => Boolean(state.flags[key]) };
});
vi.mock('@/pages/erp/erpShared', () => ({ ModuleGate: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('@/api/resources', () => ({
  listProducts: async () => [{ id: 1, name: 'Biscuits', sku: 'B-1' }, { id: 2, name: 'Flour', sku: 'F-1' }, { id: 3, name: 'Sugar', sku: 'S-1' }],
  listWarehouses: async () => [{ id: 1, name: 'Main', code: 'M' }],
  listSuppliers: async () => [],
  listCustomers: async () => [],
}));
vi.mock('@/api/mfg', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/mfg')>();
  return {
    ...actual,
    getRecipe: vi.fn(async () => {
      if (state.error) throw new Error('boom');
      return state.recipe;
    }),
    listRecipes: vi.fn(async () => (state.recipe ? [state.recipe] : [])),
    saveRecipe: vi.fn(async () => state.recipe),
    activateRecipe: vi.fn(async () => state.recipe),
    archiveRecipe: vi.fn(async () => state.recipe),
    reviseRecipe: vi.fn(async () => ({ ...(state.recipe as object), id: 99 })),
    getRouting: vi.fn(async () => ({ operations: [] })),
    saveRouting: vi.fn(async () => ({ operations: [] })),
    listWorkCentres: vi.fn(async () => []),
    getExplosion: vi.fn(async () => ({ rows: [] })),
    getWhereUsed: vi.fn(async () => ({ rows: [] })),
    getCostRollup: vi.fn(async () => ({ unitCost: '0', lines: [] })),
  };
});

import { activateRecipe, archiveRecipe, reviseRecipe, saveRecipe } from '@/api/mfg';
import { RecipePage } from './RecipePage';

const recipe = (over: Record<string, unknown> = {}) => ({
  id: 5, product: 1, name: 'Butter biscuits', status: 'DRAFT', revisionNo: 2, effectiveFrom: null, effectiveTo: null, isDefault: false,
  customer: null, parentRevision: 4, changeReason: '', outputQty: '10', yieldPct: '100', fgWarehouse: null, notes: '', isLocked: false,
  lines: [{ id: 1, component: 2, qty: '5', scrapPct: '0', issueMethod: 'MANUAL' }], outputs: [], additionalCosts: [], createdAt: '2026-10-01', ...over,
});

function open() {
  renderRoutes([{ path: '/r/:id', element: <RecipePage /> }], '/r/5');
}

describe('Recipe screen', () => {
  beforeEach(() => {
    state.role = 'OWNER';
    state.flags = {};
    state.recipe = recipe();
    state.error = false;
    vi.clearAllMocks();
  });

  it('shows the recipe with its status and revision, and its first material', async () => {
    open();
    expect(await screen.findByText(new RegExp('Butter biscuits'))).toBeTruthy();
    expect(screen.getByText(t('mfg.status.DRAFT'))).toBeTruthy();
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.recipe.tabMaterials') }));
    expect(await screen.findByDisplayValue('5')).toBeTruthy();
  });

  it('sends the edited recipe, with the added material, when saved', async () => {
    open();
    await userEvent.click(await screen.findByRole('tab', { name: t('mfg.recipe.tabMaterials') }));
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.recipe.addMaterial') }));
    const materials = await screen.findAllByLabelText(t('mfg.recipe.material'));
    await userEvent.click(materials[1]);
    await userEvent.click(await screen.findByRole('option', { name: /Sugar/ }));
    const quantities = screen.getAllByLabelText(t('mfg.common.quantity'));
    await userEvent.clear(quantities[1]);
    await userEvent.type(quantities[1], '2');
    await userEvent.click(screen.getByRole('button', { name: t('common.save') }));
    await waitFor(() => expect(saveRecipe).toHaveBeenCalledTimes(1));
    const [id, body] = vi.mocked(saveRecipe).mock.calls[0] as [number, { lines: Array<Record<string, unknown>> }];
    expect(id).toBe(5);
    expect(body.lines).toHaveLength(2);
    expect(body.lines[1]).toMatchObject({ component: 3, qty: '2', issueMethod: 'MANUAL' });
  });

  it('cannot be activated while there are unsaved edits', async () => {
    open();
    const activate = await screen.findByRole('button', { name: t('mfg.recipe.activate') });
    expect((activate as HTMLButtonElement).disabled).toBe(false);
    await userEvent.type(await screen.findByLabelText(t('mfg.recipe.changeReason')), 'less sugar');
    await waitFor(() => expect((screen.getByRole('button', { name: t('mfg.recipe.activate') }) as HTMLButtonElement).disabled).toBe(true));
  });

  it('activates a draft as the default', async () => {
    open();
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.recipe.activate') }));
    await waitFor(() => expect(activateRecipe).toHaveBeenCalledWith(5, { makeDefault: true }));
  });

  it('shows a recipe a work order has used as locked: nothing to edit, revise instead', async () => {
    state.recipe = recipe({ status: 'ACTIVE', isLocked: true, isDefault: true });
    open();
    expect(await screen.findByText(t('mfg.recipe.locked'))).toBeTruthy();
    expect((await screen.findByLabelText(t('mfg.recipe.changeReason')) as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByRole('button', { name: t('common.save') })).toBeNull();
    expect(screen.queryByRole('button', { name: t('mfg.recipe.activate') })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: t('mfg.recipe.revise') }));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeTruthy();
    expect(reviseRecipe).not.toHaveBeenCalled(); // asks for a reason first
  });

  it('archives an active recipe', async () => {
    state.recipe = recipe({ status: 'ACTIVE', isLocked: false });
    open();
    await userEvent.click(await screen.findByRole('button', { name: t('mfg.recipe.archive') }));
    await waitFor(() => expect(archiveRecipe).toHaveBeenCalledWith(5));
  });

  it('leaves a role that cannot plan with a read-only recipe', async () => {
    state.role = 'AUDITOR';
    open();
    expect((await screen.findByRole('button', { name: t('mfg.recipe.activate') }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByLabelText(t('mfg.recipe.changeReason')) as HTMLInputElement).disabled).toBe(true);
  });

  it('says so, with a retry, when the recipe cannot be loaded', async () => {
    state.error = true;
    open();
    expect(await screen.findByRole('button', { name: /retry|try again/i })).toBeTruthy();
  });
});
