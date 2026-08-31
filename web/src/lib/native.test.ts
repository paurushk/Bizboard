import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getNetworkStatus, isNative, prefsGet, prefsSet, scanBarcode } from './native';

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
});
