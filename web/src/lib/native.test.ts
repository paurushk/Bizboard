import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getNetworkStatus, isNative, onDeepLink, prefsGet, prefsSet, registerForPushNotifications, scanBarcode } from './native';

describe('native web fallbacks', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('isNative is false without Capacitor', () => {
    expect(isNative()).toBe(false);
  });

  it('getNetworkStatus uses navigator.onLine', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
    await expect(getNetworkStatus()).resolves.toEqual({ connected: false });
  });

  it('prefsGet/Set use localStorage on web', async () => {
    await prefsSet('k', 'v');
    await expect(prefsGet('k')).resolves.toBe('v');
  });

  it('scanBarcode returns null when detector is missing', async () => {
    await expect(scanBarcode()).resolves.toBeNull();
  });

  it('stops camera tracks when detect fails', async () => {
    const stop = vi.fn();
    const stream = {
      getVideoTracks: () => [{ stop }],
      getTracks: () => [{ stop }],
    };
    class FakeDetector {
      detect() {
        return Promise.reject(new Error('no code'));
      }
    }
    vi.stubGlobal('BarcodeDetector', FakeDetector);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: async () => stream },
    });
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined as never);
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
      drawImage: vi.fn(),
    } as unknown as CanvasRenderingContext2D);
    await expect(scanBarcode()).resolves.toBeNull();
    expect(stop).toHaveBeenCalled();
  });

  it('registerForPushNotifications is a no-op on web (not native)', async () => {
    await expect(registerForPushNotifications()).resolves.toBeNull();
  });

  it('registerForPushNotifications resolves the token once permission is granted and registration fires', async () => {
    const addListener = vi.fn((event: string, cb: (data: unknown) => void) => {
      if (event === 'registration') {
        // Fire on next tick, like the real native bridge would.
        queueMicrotask(() => cb({ value: 'device-token-123' }));
      }
      return Promise.resolve({ remove: vi.fn() });
    });
    vi.stubGlobal('Capacitor', {
      isNativePlatform: () => true,
      Plugins: {
        PushNotifications: {
          requestPermissions: async () => ({ receive: 'granted' }),
          register: async () => {},
          addListener,
        },
      },
    });
    await expect(registerForPushNotifications()).resolves.toBe('device-token-123');
  });

  it('registerForPushNotifications resolves null when permission is denied', async () => {
    vi.stubGlobal('Capacitor', {
      isNativePlatform: () => true,
      Plugins: {
        PushNotifications: {
          requestPermissions: async () => ({ receive: 'denied' }),
          register: async () => {},
          addListener: vi.fn(async () => ({ remove: vi.fn() })),
        },
      },
    });
    await expect(registerForPushNotifications()).resolves.toBeNull();
  });

  it('onDeepLink is a no-op unsubscribe on web (not native)', () => {
    const cb = vi.fn();
    const unsubscribe = onDeepLink(cb);
    expect(cb).not.toHaveBeenCalled();
    expect(() => unsubscribe()).not.toThrow();
  });

  it('onDeepLink invokes the callback with the opened URL when native', async () => {
    const remove = vi.fn();
    const state: { fired: ((data: { url: string }) => void) | null } = { fired: null };
    vi.stubGlobal('Capacitor', {
      isNativePlatform: () => true,
      Plugins: {
        App: {
          addListener: vi.fn((_event: string, cb: (data: { url: string }) => void) => {
            state.fired = cb;
            return Promise.resolve({ remove });
          }),
        },
      },
    });
    const cb = vi.fn();
    const unsubscribe = onDeepLink(cb);
    // Let the addListener promise resolve before firing / unsubscribing.
    await Promise.resolve();
    state.fired?.({ url: 'in.bizboard.app://invoices/123' });
    expect(cb).toHaveBeenCalledWith('in.bizboard.app://invoices/123');
    unsubscribe();
    expect(remove).toHaveBeenCalled();
  });
});
