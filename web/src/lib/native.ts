/** Native/WebView adapters. Web keeps working when Capacitor is absent. */

export type NetworkStatus = { connected: boolean };

type PushToken = { value: string };
type PushError = { error: string };
type PushNotificationsPlugin = {
  requestPermissions?: () => Promise<{ receive: 'granted' | 'denied' | 'prompt' }>;
  register?: () => Promise<void>;
  addListener?: (
    event: 'registration' | 'registrationError',
    cb: (data: PushToken | PushError) => void,
  ) => Promise<{ remove: () => void }>;
};

type AppUrlOpenData = { url: string };
type AppPlugin = {
  addListener?: (
    event: 'appUrlOpen',
    cb: (data: AppUrlOpenData) => void,
  ) => Promise<{ remove: () => void }>;
};

type CapacitorBridge = {
  isNativePlatform?: () => boolean;
  Plugins?: Record<string, { getStatus?: () => Promise<NetworkStatus>; addListener?: (...args: unknown[]) => unknown }> & {
    PushNotifications?: PushNotificationsPlugin;
    App?: AppPlugin;
  };
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

/**
 * M1-009: register this device for push notifications. No-ops on web (not
 * native) or if the plugin isn't present (e.g. no google-services.json was
 * bundled, so `PushNotifications` never registers with the WebView bridge).
 * Resolves with the device token once Capacitor's `registration` event
 * fires, or `null` on denial/error/timeout — callers PATCH it to
 * `/auth/me/`. Never throws.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  const cap = capacitor();
  const plugin = cap?.Plugins?.PushNotifications;
  if (!isNative() || !plugin?.requestPermissions || !plugin.register || !plugin.addListener) {
    return null;
  }
  try {
    const perm = await plugin.requestPermissions();
    if (perm.receive !== 'granted') return null;
    return await new Promise<string | null>((resolve) => {
      let settled = false;
      const finish = (value: string | null) => {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      // Belt-and-suspenders: registration should fire quickly; don't hang
      // the caller forever if the native side never responds.
      const timer = setTimeout(() => finish(null), 10_000);
      void plugin
        .addListener!('registration', (data) => {
          clearTimeout(timer);
          finish('value' in data ? data.value : null);
        })
        .catch(() => finish(null));
      void plugin
        .addListener!('registrationError', () => {
          clearTimeout(timer);
          finish(null);
        })
        .catch(() => {});
      void plugin.register!().catch(() => finish(null));
    });
  } catch {
    return null;
  }
}

/**
 * M1-008: subscribe to a custom-scheme deep link being opened while the app
 * is already running (`onNewIntent` -> Capacitor's `App.appUrlOpen`). `cb`
 * receives the full URL (e.g. `in.bizboard.app://invoices/123`) — callers
 * strip the scheme/host and navigate. No-ops on web or if `@capacitor/app`
 * isn't present. Returns an unsubscribe function (always safe to call).
 */
export function onDeepLink(cb: (url: string) => void): () => void {
  const plugin = capacitor()?.Plugins?.App;
  if (!isNative() || !plugin?.addListener) return () => {};
  let handle: { remove: () => void } | null = null;
  void plugin
    .addListener('appUrlOpen', (data) => cb(data.url))
    .then((h) => {
      handle = h;
    })
    .catch(() => {});
  return () => handle?.remove();
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
