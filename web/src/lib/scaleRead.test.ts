import { afterEach, describe, expect, it, vi } from 'vitest';
import { readScaleWeight } from '@/lib/native';

type Chunk = string | 'END';

function fakePort(chunks: Chunk[]) {
  const encoder = new TextEncoder();
  const queue = [...chunks];
  const close = vi.fn(async () => undefined);
  const cancel = vi.fn(async () => undefined);
  const release = vi.fn();
  const port = {
    open: vi.fn(async () => undefined),
    close,
    readable: {
      getReader: () => ({
        read: async () => {
          const next = queue.shift();
          if (next === undefined || next === 'END') return { value: undefined, done: true };
          return { value: encoder.encode(next), done: false };
        },
        cancel,
        releaseLock: release,
      }),
    },
  };
  return { port, close, cancel, release };
}

function withSerial(ports: unknown[], requestPort: () => Promise<unknown> = async () => ports[0]) {
  Object.defineProperty(navigator, 'serial', {
    configurable: true,
    value: { getPorts: async () => ports, requestPort },
  });
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'serial');
});

describe('readScaleWeight', () => {
  it('joins a line that arrives in two reads', async () => {
    const { port, close } = fakePort(['ST,GS,  1.2', '50 kg\r\n']);
    withSerial([port]);
    expect(await readScaleWeight()).toBe(1.25);
    expect(close).toHaveBeenCalled();
  });

  it('refuses an unstable reading', async () => {
    const { port } = fakePort(['US,GS,  1.250 kg\r\n']);
    withSerial([port]);
    expect(await readScaleWeight()).toBeNull();
  });

  it('ignores a half line that never ends', async () => {
    const { port } = fakePort(['ST,GS,  1.2', 'END']);
    withSerial([port]);
    expect(await readScaleWeight()).toBeNull();
  });

  it('uses the last complete line', async () => {
    const { port } = fakePort(['ST,GS,  0.500 kg\r\nST,GS,  0.750 kg\r\n']);
    withSerial([port]);
    expect(await readScaleWeight()).toBe(0.75);
  });

  it('reuses a granted port and only asks when there is none', async () => {
    const request = vi.fn(async () => fakePort(['ST,GS,  2.000 kg\n']).port);
    withSerial([], request);
    expect(await readScaleWeight()).toBe(2);
    expect(request).toHaveBeenCalledTimes(1);
    const granted = fakePort(['ST,GS,  3.000 kg\n']).port;
    const again = vi.fn();
    withSerial([granted], again);
    expect(await readScaleWeight()).toBe(3);
    expect(again).not.toHaveBeenCalled();
  });

  it('returns null and closes the port when the read throws', async () => {
    const close = vi.fn(async () => undefined);
    const port = {
      open: async () => undefined,
      close,
      readable: {
        getReader: () => ({
          read: async () => {
            throw new Error('unplugged');
          },
          cancel: async () => undefined,
          releaseLock: () => undefined,
        }),
      },
    };
    withSerial([port]);
    expect(await readScaleWeight()).toBeNull();
    expect(close).toHaveBeenCalled();
  });

  it('is a no-op in a browser with no serial port', async () => {
    expect(await readScaleWeight()).toBeNull();
  });
});
