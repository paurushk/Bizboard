import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

function Bomb(): never {
  throw new Error('boom');
}

function ThrowsMessage({ message }: { message: string }): never {
  throw new Error(message);
}

describe('ErrorBoundary', () => {
  it('BUG-409: renders a fallback instead of a blank screen when a child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  it('renders children normally when nothing throws', () => {
    render(
      <ErrorBoundary>
        <div>all good</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('all good')).toBeInTheDocument();
  });

  describe('FE-11 / BB-000829: chunk-load auto-reload', () => {
    afterEach(() => {
      vi.restoreAllMocks();
      try {
        sessionStorage.removeItem('bizboard:chunk-reload');
      } catch {
        /* ignore */
      }
    });

    // A stale index.html referencing a chunk hash the server no longer has
    // (a deploy landed, or a deep link forced a code-split route to load
    // before the auth guard could redirect away) surfaces as a dynamic
    // import() rejection — but every browser engine phrases that rejection
    // differently. Each of these is a real message this app has hit in the
    // wild; missing one silently turns a self-healing reload into the
    // "Something went wrong" dead end for that browser only.
    const chunkErrorMessages = [
      'ChunkLoadError',
      'Loading chunk 4 failed',
      'Failed to fetch dynamically imported module: https://app/assets/x.js',
      'error loading dynamically imported module',
      // Reproduces the exact wording hit navigating straight to /sales/new
      // while logged out: the browser's generic dynamic-import failure text,
      // which the original regex did not match.
      'TypeError: An unknown error occurred when fetching the script.',
      "TypeError: import() failed: module script failed to load",
      'NetworkError when attempting to fetch resource.',
    ];

    it.each(chunkErrorMessages)(
      'auto-reloads once instead of stranding the user for: %s',
      (message) => {
        vi.spyOn(console, 'error').mockImplementation(() => {});
        const reload = vi.fn();
        vi.stubGlobal('location', { ...window.location, reload });

        render(
          <ErrorBoundary>
            <ThrowsMessage message={message} />
          </ErrorBoundary>,
        );

        expect(reload).toHaveBeenCalledTimes(1);
      },
    );

    it('does not auto-reload (and shows the fallback) for a non-chunk error', () => {
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const reload = vi.fn();
      vi.stubGlobal('location', { ...window.location, reload });

      render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>,
      );

      expect(reload).not.toHaveBeenCalled();
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });
});
