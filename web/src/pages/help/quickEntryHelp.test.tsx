import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PageTitle, resolveContextHelpPage } from '@/contextHelp';
import { getContextHelpPage } from '@/contextHelp/catalog';
import { HelpPageV0 } from './HelpPageV0';
import { en } from '@/i18n';
import { FAQ_CATEGORIES, FAQ_ITEMS } from './faqContent';

function faqText(id: string): string {
  const item = FAQ_ITEMS.find((row) => row.id === id);
  expect(item, id).toBeTruthy();
  return render(<>{item!.answer}</>).container.textContent ?? '';
}

const QUICK_ENTRY_FAQS = [
  'quick-entry-order',
  'quick-entry-order-vs-bill',
  'quick-entry-price',
  'quick-entry-needs-approval',
  'quick-entry-blocked-customer',
  'quick-entry-quantity',
  'quick-entry-draft-recovery',
  'quick-entry-offline',
  'quick-entry-warnings',
  'quick-entry-duplicates',
  'quick-entry-delivery-details',
  'quick-entry-where-saved',
  'quick-entry-gst',
  'quick-entry-turn-on',
];

describe('quick order entry help page', () => {
  const page = getContextHelp();

  function getContextHelp() {
    return getContextHelpPage('quick-entry');
  }

  it('is shown on the Quick Entry route', () => {
    expect(resolveContextHelpPage('/sales/quick-entry')).toBe('quick-entry');
  });

  it('has a Hindi line for every section it shows', () => {
    expect(page).toBeTruthy();
    const parts = [
      page!.summary,
      ...page!.howItWorks,
      ...page!.businessImpact,
      ...page!.keyRules,
      ...page!.commonMistakes,
      ...page!.nextActions,
    ];
    for (const part of parts) expect(part.hi?.trim(), part.en).toBeTruthy();
  });

  it('explains price, quantity, modes, drafts, duplicates and approvals', () => {
    const text = [page!.summary, ...page!.howItWorks, ...page!.keyRules, ...page!.businessImpact]
      .map((part) => part.en)
      .join('\n');
    expect(text).toMatch(/price list/);
    expect(text).toMatch(/Undo/);
    expect(text).toMatch(/Sales order/);
    expect(text).toMatch(/Draft bill/);
    expect(text).toMatch(/Resume/);
    expect(text).toMatch(/second document/);
    expect(text).toMatch(/Needs approval/);
    expect(text).toMatch(/delivery address/);
  });

  it('links to the pages a rep goes on to', () => {
    const paths = page!.relatedPages.map((row) => row.path);
    for (const path of ['/sales/orders', '/sales/history', '/sales/customers', '/sales/delivery-routes']) {
      expect(paths).toContain(path);
    }
    for (const row of page!.relatedPages) {
      const key = row.labelKey.replace(/^nav\./, '');
      expect((en as unknown as { nav: Record<string, string> }).nav[key], row.labelKey).toBeTruthy();
    }
  });
});

describe('quick order entry FAQs', () => {
  it('are all present, in a known category, with unique ids', () => {
    const ids = FAQ_ITEMS.map((row) => row.id);
    for (const id of QUICK_ENTRY_FAQS) expect(ids, id).toContain(id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of QUICK_ENTRY_FAQS) {
      expect(FAQ_CATEGORIES).toContain(FAQ_ITEMS.find((row) => row.id === id)!.category);
    }
  });

  it('answer the questions a rep actually asks', () => {
    expect(faqText('quick-entry-order-vs-bill')).toMatch(/draft bill/i);
    expect(faqText('quick-entry-order-vs-bill')).toMatch(/reserves stock/);
    expect(faqText('quick-entry-price')).toMatch(/price list/);
    expect(faqText('quick-entry-price')).toMatch(/estimated GST/);
    expect(faqText('quick-entry-needs-approval')).toMatch(/Needs approval/);
    expect(faqText('quick-entry-needs-approval')).toMatch(/Confirm/);
    expect(faqText('quick-entry-blocked-customer')).toMatch(/blocked/i);
    expect(faqText('quick-entry-quantity')).toMatch(/Undo/);
    expect(faqText('quick-entry-quantity')).toMatch(/three places/);
    expect(faqText('quick-entry-draft-recovery')).toMatch(/Resume/);
    expect(faqText('quick-entry-draft-recovery')).toMatch(/never stores prices/);
    expect(faqText('quick-entry-offline')).toMatch(/Saving needs a connection/);
    expect(faqText('quick-entry-warnings')).toMatch(/credit limit/);
    expect(faqText('quick-entry-duplicates')).toMatch(/two documents/);
    expect(faqText('quick-entry-delivery-details')).toMatch(/default saved address/);
    expect(faqText('quick-entry-where-saved')).toMatch(/Open/);
    expect(faqText('quick-entry-gst')).toMatch(/Composition/);
    expect(faqText('quick-entry-turn-on')).toMatch(/administrator/);
  });

  it('keywords make them findable', () => {
    const item = (id: string) => FAQ_ITEMS.find((row) => row.id === id)!;
    expect(item('quick-entry-price').keywords).toContain('price list');
    expect(item('quick-entry-needs-approval').keywords).toContain('needs approval');
    expect(item('quick-entry-draft-recovery').keywords).toContain('resume order');
  });
});


describe('quick order entry help in the app', () => {
  it('opens from the page help button and shows the sections without leaving the screen', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/sales/quick-entry']}>
        <Routes>
          <Route
            path="/sales/quick-entry"
            element={
              <PageTitle>Quick order entry</PageTitle>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    await user.click(screen.getByTestId('context-help-trigger'));
    const drawer = await screen.findByTestId('context-help-drawer');
    expect(drawer).toHaveTextContent('Quick order entry');
    expect(drawer).toHaveTextContent('What this page is for');
    expect(drawer).toHaveTextContent('Needs approval');
    expect(drawer).toHaveTextContent('price list');
    expect(drawer).toHaveTextContent('Sales Orders');
  });

  it('does not leave an unresolved t: token in any quick-entry FAQ', () => {
    for (const id of QUICK_ENTRY_FAQS) {
      expect(faqText(id), id).not.toMatch(/t:[a-z]+\.[A-Za-z0-9]+/);
      expect(faqText(id), id).not.toMatch(/\*\*/);
    }
  });

  it('every FAQ has a distinct question and a non-trivial answer', () => {
    const questions = QUICK_ENTRY_FAQS.map((id) => FAQ_ITEMS.find((row) => row.id === id)!.question);
    expect(new Set(questions).size).toBe(questions.length);
    for (const id of QUICK_ENTRY_FAQS) expect(faqText(id).length, id).toBeGreaterThan(120);
  });
});

describe('quick order entry FAQs on the Help page', () => {
  const scroll = vi.fn();

  beforeEach(() => {
    scroll.mockClear();
    Element.prototype.scrollIntoView = scroll;
  });

  afterEach(() => {
    // @ts-expect-error jsdom has no scrollIntoView; remove the stub again
    delete Element.prototype.scrollIntoView;
  });

  const open = (hash = '') =>
    render(
      <MemoryRouter initialEntries={[`/help${hash}`]}>
        <HelpPageV0 />
      </MemoryRouter>,
    );

  it('are listed under the orders category', () => {
    open();
    expect(screen.getByText('How do I book an order quickly from the road?')).toBeInTheDocument();
    expect(screen.getByText('Quotations, orders & challans')).toBeInTheDocument();
  });

  it.each([
    ['needs approval', 'Quick order entry says “Needs approval” or “confirming did not complete”. What now?'],
    ['price list', 'Why is the price on Quick order entry different from the item’s selling price?'],
    ['resume order', 'I closed the page in the middle of an order. Is it lost?'],
    ['double tap', 'What if I tap Save twice, or save again after an error?'],
    ['deliver to', 'Where do the delivery address, notes and payment terms come from?'],
  ])('search for “%s” finds its question and hides unrelated ones', (term, question) => {
    open();
    fireEvent.change(screen.getByLabelText(/search faqs/i), { target: { value: term } });
    expect(screen.getByText(question)).toBeInTheDocument();
    expect(screen.queryByText('Where is goods received (GRN)?')).not.toBeInTheDocument();
  });

  it('a deep link opens the entry and shows its answer', async () => {
    open('#quick-entry-quantity');
    const question = screen.getByRole('button', {
      name: 'How do I enter a large or fractional quantity, and how do I remove a line?',
    });
    expect(question.getAttribute('aria-expanded')).toBe('true');
    expect(await screen.findByText(/accept decimals up to three places/)).toBeInTheDocument();
    await waitFor(() => expect(scroll).toHaveBeenCalled());
  });
});
