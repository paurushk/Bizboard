import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { ModuleNotReady } from './ModuleNotReady';

describe('ModuleNotReady', () => {
  it('keeps a heading and the explanation on the page', () => {
    render(
      <MemoryRouter>
        <ModuleNotReady message="Journals could not be listed." />
      </MemoryRouter>,
    );
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/not ready/i);
    expect(screen.getByText('Journals could not be listed.')).toBeInTheDocument();
  });
});
