import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { AxiosError } from 'axios';
import { HelpErrorAlert } from './HelpErrorAlert';

/**
 * §H1 — the BE 4xx → HelpCode → user-message contract, on the render side.
 * `getErrorMessage` / `getErrorCode` parsing is unit-tested in
 * src/api/client.test.ts; this pins that HelpErrorAlert actually surfaces the
 * parsed message as an assertive alert (not a raw JSON dump, not silent).
 */
function envelopeError(code: string, message: string, details?: unknown): AxiosError {
  return {
    isAxiosError: true,
    name: 'AxiosError',
    message: 'Request failed',
    toJSON: () => ({}),
    config: {} as never,
    response: {
      status: 400,
      statusText: 'Bad Request',
      headers: {},
      config: {} as never,
      data: { error: { code, message, ...(details ? { details } : {}) }, success: false },
    },
  } as AxiosError;
}

function renderAlert(error: unknown) {
  return render(
    <MemoryRouter>
      <HelpErrorAlert error={error} />
    </MemoryRouter>,
  );
}

describe('HelpErrorAlert — BE error → user message', () => {
  it('renders the envelope message as an assertive error alert', () => {
    renderAlert(envelopeError('insufficient_stock', 'Insufficient stock for Premium Tea 500g'));
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Insufficient stock for Premium Tea 500g');
    expect(alert.getAttribute('aria-live')).toBe('polite');
  });

  it('joins field-level details when the message is a generic "Validation failed"', () => {
    renderAlert(
      envelopeError('validation_error', 'Validation failed', {
        gstin: ['Enter a valid GSTIN.'],
        phone: ['Required.'],
      }),
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('gstin: Enter a valid GSTIN.');
    expect(alert).toHaveTextContent('phone: Required.');
    // never leaks the raw envelope
    expect(alert.textContent).not.toContain('{');
  });

  it('an explicit message prop wins over the error object', () => {
    renderAlert(envelopeError('x', 'ignored'));
    render(
      <MemoryRouter>
        <HelpErrorAlert message="This bill is already cancelled." error={envelopeError('x', 'ignored')} />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole('alert').some((el) => el.textContent?.includes('already cancelled'))).toBe(
      true,
    );
  });

  it('renders nothing when there is no message and no error', () => {
    const { container } = render(
      <MemoryRouter>
        <HelpErrorAlert />
      </MemoryRouter>,
    );
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('shows Support ID on a 500 envelope and not on a 400', () => {
    const five = envelopeError('server_error', 'An unexpected error occurred.');
    five.response = {
      ...five.response!,
      status: 500,
      statusText: 'Error',
      data: {
        success: false,
        error: {
          code: 'server_error',
          message: 'An unexpected error occurred.',
          request_id: 'rid-help',
        },
      },
    };
    renderAlert(five);
    expect(screen.getByRole('alert')).toHaveTextContent('Support ID: rid-help');

    renderAlert(envelopeError('validation_error', 'GSTIN is required.'));
    const alerts = screen.getAllByRole('alert');
    expect(alerts.some((el) => el.textContent?.includes('GSTIN is required'))).toBe(true);
    expect(alerts.filter((el) => el.textContent?.includes('GSTIN is required'))[0].textContent).not.toContain(
      'Support ID',
    );
  });
});
