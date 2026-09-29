/** Queue a proof-of-delivery photo with its delivery record until the device is online. */

import { setDeliveryRouteStopStatus, uploadFile } from '@/api/legacy/sales';

const DB_NAME = 'bizboard-pod';
const STORE = 'photos';

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      return reject(new Error('IndexedDB not supported'));
    }
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE, { keyPath: 'id' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export interface QueuedPodPhoto {
  id: string;
  dataUrl: string;
  record: {
    routeId?: number | string;
    stopId?: number | string;
    [key: string]: unknown;
  };
  queuedAt: number;
}

export async function queuePodPhoto(id: string, dataUrl: string, record: Record<string, unknown>): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put({ id, dataUrl, record, queuedAt: Date.now() });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

function dataUrlToFile(dataUrl: string, filename: string): File {
  const arr = dataUrl.split(',');
  const mime = arr[0].match(/:(.*?);/)?.[1] || 'image/jpeg';
  const bstr = atob(arr[1]);
  let n = bstr.length;
  const u8arr = new Uint8Array(n);
  while (n--) {
    u8arr[n] = bstr.charCodeAt(n);
  }
  return new File([u8arr], filename, { type: mime });
}

/** Drain and upload all queued POD photos to the backend server. */
export async function drainPodPhotos(): Promise<number> {
  if (typeof window === 'undefined' || typeof indexedDB === 'undefined' || !navigator.onLine) {
    return 0;
  }
  let db: IDBDatabase;
  try {
    db = await openDb();
  } catch {
    return 0;
  }

  const items = await new Promise<QueuedPodPhoto[]>((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const store = tx.objectStore(STORE);
    const req = store.getAll();
    req.onsuccess = () => resolve((req.result as QueuedPodPhoto[]) || []);
    req.onerror = () => reject(req.error);
  }).catch(() => [] as QueuedPodPhoto[]);
  db.close();

  if (!items.length) return 0;
  let drained = 0;

  for (const item of items) {
    try {
      const file = dataUrlToFile(item.dataUrl, `pod-${item.id}.jpg`);
      const uploaded = await uploadFile(file, 'ATTACHMENT');
      if (uploaded?.id != null && item.record?.routeId != null && item.record?.stopId != null) {
        await setDeliveryRouteStopStatus(
          Number(item.record.routeId),
          Number(item.record.stopId),
          'DELIVERED',
          {
            podPhoto: uploaded.id,
            podNote: 'photo',
            receivedByName: String(item.record.receivedByName || '').trim() || undefined,
          },
        );
      }
      const writeDb = await openDb();
      await new Promise<void>((resolve, reject) => {
        const delTx = writeDb.transaction(STORE, 'readwrite');
        delTx.objectStore(STORE).delete(item.id);
        delTx.oncomplete = () => resolve();
        delTx.onerror = () => reject(delTx.error);
      });
      writeDb.close();
      drained++;
    } catch {
      // Leave queued for next retry
    }
  }
  return drained;
}
