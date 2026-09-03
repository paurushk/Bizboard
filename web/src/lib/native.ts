/** Native/WebView adapters. Web keeps working when Capacitor is absent. */

export type NetworkStatus = { connected: boolean };

type CapacitorBridge = {
  isNativePlatform?: () => boolean;
  Plugins?: Record<string, { getStatus?: () => Promise<NetworkStatus>; addListener?: (...args: unknown[]) => unknown }>;
};

function capacitor(): CapacitorBridge | null {
  if (typeof window === 'undefined') return null;
  return (window as unknown as { Capacitor?: CapacitorBridge }).Capacitor ?? null;
}

export function isNative(): boolean {
  try {
    return Boolean(capacitor()?.isNativePlatform?.());
  } catch {
    return false;
  }
}

export async function getNetworkStatus(): Promise<NetworkStatus> {
  const cap = capacitor();
  if (isNative() && cap?.Plugins?.Network?.getStatus) {
    try {
      return await cap.Plugins.Network.getStatus();
    } catch {
      /* fall through */
    }
  }
  return { connected: typeof navigator === 'undefined' ? true : navigator.onLine };
}

function waitFrame(): Promise<void> {
  return new Promise((resolve) => {
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => resolve());
      return;
    }
    setTimeout(resolve, 16);
  });
}

export async function scanBarcode(): Promise<string | null> {
  const Detector = (globalThis as unknown as { BarcodeDetector?: new (opts: { formats: string[] }) => { detect: (src: ImageBitmapSource) => Promise<Array<{ rawValue?: string }>> } }).BarcodeDetector;
  if (typeof Detector !== 'function' || typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    if (isNative()) {
      throw new Error(
        'Barcode scanning is not available in this packaged build. Type the code, or use Chrome on the web.',
      );
    }
    return null;
  }
  let stream: MediaStream | null = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    const detector = new Detector({ formats: ['ean_13', 'ean_8', 'code_128', 'qr_code'] });
    const video = document.createElement('video');
    video.setAttribute('playsinline', 'true');
    video.muted = true;
    video.srcObject = stream;
    let timeoutId = 0;
    const waitReady = new Promise<void>((resolve) => {
      const done = () => {
        window.clearTimeout(timeoutId);
        resolve();
      };
      video.addEventListener('loadeddata', done, { once: true });
      video.addEventListener('loadedmetadata', done, { once: true });
      timeoutId = window.setTimeout(done, 250);
    });
    await video.play().catch(() => undefined);
    await waitReady;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const frames = typeof requestAnimationFrame === 'function' ? 8 : 1;
    for (let i = 0; i < frames; i += 1) {
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      ctx?.drawImage(video, 0, 0);
      const codes = await detector.detect(canvas);
      const value = codes[0]?.rawValue?.trim();
      if (value) return value;
      await waitFrame();
    }
    return null;
  } catch {
    return null;
  } finally {
    stream?.getTracks().forEach((t) => t.stop());
  }
}

export async function prefsGet(key: string): Promise<string | null> {
  const cap = capacitor();
  const prefs = cap?.Plugins?.Preferences as { get?: (opts: { key: string }) => Promise<{ value?: string | null }> } | undefined;
  if (isNative() && prefs?.get) {
    try {
      const row = await prefs.get({ key });
      return row.value ?? null;
    } catch {
      /* fall through */
    }
  }
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export async function prefsSet(key: string, value: string, opts?: { skipLocal?: boolean }): Promise<void> {
  const cap = capacitor();
  const prefs = cap?.Plugins?.Preferences as { set?: (opts: { key: string; value: string }) => Promise<void> } | undefined;
  if (isNative() && prefs?.set) {
    try {
      await prefs.set({ key, value });
    } catch {
      /* still write local unless skipped */
    }
  }
  if (opts?.skipLocal) return;
  try {
    localStorage.setItem(key, value);
  } catch (err) {
    const quota = err instanceof DOMException && (
      err.name === 'QuotaExceededError' || err.code === 22 || err.code === 1014
    );
    if (quota) {
      throw new Error('OUTBOX_STORAGE_FULL');
    }
    throw err;
  }
}

export async function registerPushToken(token: string): Promise<void> {
  if (!token.trim()) return;
  const { apiClient } = await import('@/api/client');
  await apiClient.patch('/auth/me/', { pushToken: token.trim() });
}
