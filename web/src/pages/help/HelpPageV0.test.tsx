import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setLocale } from '@/i18n';
import { HelpPageV0 } from './HelpPageV0';

describe('HelpPageV0 FAQ catalog', () => {
  it('shows original conversion FAQ and new sections', () => {
    render(
      <MemoryRouter>
        <HelpPageV0 />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/How do I set the conversion rate between a base unit and an alternate unit/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Getting started')).toBeInTheDocument();
    expect(screen.getByText('Where is goods received (GRN)?')).toBeInTheDocument();
    expect(screen.getByText('Does Bizboard file GSTR-1 or GSTR-3B on the GST portal?')).toBeInTheDocument();
  });

  it('search matches a new keyword and hides unrelated questions', () => {
    render(
      <MemoryRouter>
        <HelpPageV0 />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText(/search faqs/i), { target: { value: 'grn' } });
    expect(screen.getByText('Where is goods received (GRN)?')).toBeInTheDocument();
    expect(
      screen.queryByText(/How do I set the conversion rate between a base unit and an alternate unit/i),
    ).not.toBeInTheDocument();
  });

  it('mounts an answer only once its question is opened (BB-100: /help rendered blank for seconds)', async () => {
    render(
      <MemoryRouter>
        <HelpPageV0 />
      </MemoryRouter>,
    );
    const answer = /Rejected quantity drafts a supplier debit note/;
    expect(screen.queryByText(answer)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Where is goods received (GRN)?' }));
    expect(await screen.findByText(answer)).toBeInTheDocument();
  });
});

describe('HelpPageV0 deep links', () => {
  const QUESTION = /How do I set the conversion rate between a base unit and an alternate unit/i;
  const scroll = vi.fn();

  beforeEach(() => {
    scroll.mockClear();
    Element.prototype.scrollIntoView = scroll;
  });

  afterEach(() => {
    // @ts-expect-error jsdom has no scrollIntoView; remove the stub again
    delete Element.prototype.scrollIntoView;
  });

  const open = (hash: string) =>
    render(
      <MemoryRouter initialEntries={[`/help${hash}`]}>
        <HelpPageV0 />
      </MemoryRouter>,
    );

  it('opens the entry named in the address and scrolls to it', async () => {
    open('#unit-conversion-rate');
    const question = screen.getByRole('button', { name: QUESTION });
    expect(question.getAttribute('aria-expanded')).toBe('true');
    await waitFor(() => expect(scroll).toHaveBeenCalledTimes(1));
  });

  it('leaves every entry closed when there is no link', () => {
    open('');
    expect(screen.getByRole('button', { name: QUESTION }).getAttribute('aria-expanded')).toBe('false');
    expect(scroll).not.toHaveBeenCalled();
  });

  it('ignores a link to an entry that does not exist', async () => {
    open('#no-such-entry');
    expect(screen.getByRole('button', { name: QUESTION }).getAttribute('aria-expanded')).toBe('false');
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(scroll).not.toHaveBeenCalled();
  });
});

/** BB-100 F4: the machine-drafted Hindi shows when Hindi is selected; English stays the fallback. */
describe('HelpPageV0 in Hindi', () => {
  afterEach(() => setLocale('en'));

  it('shows the Hindi question and answer, says it is a draft, and finds Hindi search words', async () => {
    setLocale('hi');
    render(
      <MemoryRouter>
        <HelpPageV0 />
      </MemoryRouter>,
    );
    expect(screen.getByText(/मशीन से अनुवादित/)).toBeInTheDocument();
    const question = screen.getByRole('button', { name: 'मूल इकाई और वैकल्पिक इकाई के बीच कन्वर्ज़न दर कैसे सेट करें?' });
    fireEvent.click(question);
    expect(question.getAttribute('aria-expanded')).toBe('true');
    expect(screen.queryByText(/sit in one alternate unit/i)).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'कन्वर्ज़न' } });
    expect(screen.getByRole('button', { name: /कन्वर्ज़न दर/ })).toBeInTheDocument();
  });
});

