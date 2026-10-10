// @vitest-environment node
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// The Docker web image runs `npm ci`, which refuses a tree whose peers do not match. Dependabot
// bumps one package of a pair at a time (react 19 with react-dom 18, @eslint/js 10 with eslint 9,
// x-date-pickers 9 with MUI 6), and that broke the image build while local installs still worked.

const require = createRequire(import.meta.url);
const semver = require('semver') as {
  major(version: string): number;
  minVersion(range: string): { version: string } | null;
  satisfies(version: string, range: string, options?: { includePrerelease?: boolean }): boolean;
};

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..');

type Manifest = {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  overrides?: Record<string, unknown>;
};
type LockEntry = Manifest & {
  version?: string;
  peerDependencies?: Record<string, string>;
  peerDependenciesMeta?: Record<string, { optional?: boolean }>;
};

const pkg = JSON.parse(readFileSync(join(WEB, 'package.json'), 'utf8')) as Manifest;
const lock = JSON.parse(readFileSync(join(WEB, 'package-lock.json'), 'utf8')) as {
  packages: Record<string, LockEntry>;
};
const direct: Record<string, string> = { ...pkg.dependencies, ...pkg.devDependencies };
const installed = (name: string) => lock.packages[`node_modules/${name}`]?.version;
const declaredMajor = (name: string) => semver.major(semver.minVersion(direct[name])?.version ?? '0.0.0');

describe('web package alignment', () => {
  it.each([
    ['react-dom', 'react'],
    ['@types/react', 'react'],
    ['@types/react-dom', 'react-dom'],
    ['@eslint/js', 'eslint'],
  ])('%s is on the same major as %s', (name, partner) => {
    if (!direct[name] || !direct[partner]) return;
    expect(declaredMajor(name)).toBe(declaredMajor(partner));
  });

  it('package-lock.json was regenerated after the last package.json edit', () => {
    const root = lock.packages[''];
    expect(root.dependencies ?? {}).toEqual(pkg.dependencies ?? {});
    expect(root.devDependencies ?? {}).toEqual(pkg.devDependencies ?? {});
    const stale = Object.entries(direct)
      .filter(([name, range]) => {
        const version = installed(name);
        return version && semver.minVersion(range) && !semver.satisfies(version, range, { includePrerelease: true });
      })
      .map(([name, range]) => `${name}: locked ${installed(name)}, wants ${range}`);
    expect(stale).toEqual([]);
  });

  it('every direct dependency satisfies the peers it shares with this app', () => {
    const overridden = new Set(Object.keys(pkg.overrides ?? {}));
    const broken: string[] = [];
    for (const name of Object.keys(direct)) {
      const entry = lock.packages[`node_modules/${name}`];
      for (const [peer, range] of Object.entries(entry?.peerDependencies ?? {})) {
        if (!direct[peer] || overridden.has(peer) || entry?.peerDependenciesMeta?.[peer]?.optional) continue;
        const version = installed(peer);
        if (version && !semver.satisfies(version, range, { includePrerelease: true })) {
          broken.push(`${name} needs ${peer} ${range}, locked ${version}`);
        }
      }
    }
    expect(broken).toEqual([]);
  });
});
