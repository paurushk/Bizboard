/** Generic ASCII scale line. A leading status token can mark a stable reading. */

export function parseScaleReading(
  raw: string,
  pattern = /([+-]?\d+(?:\.\d+)?)/,
): { weight: number; stable: boolean } | null {
  const text = raw.trim();
  if (!text) return null;
  const stable = /^(ST|S|STABLE)\b/i.test(text) || !/^(US|UNSTABLE)\b/i.test(text);
  if (/^(US|UNSTABLE)\b/i.test(text)) {
    const match = pattern.exec(text);
    if (!match) return null;
    return { weight: Number(match[1]), stable: false };
  }
  const match = pattern.exec(text);
  if (!match) return null;
  const weight = Number(match[1]);
  if (!Number.isFinite(weight)) return null;
  return { weight, stable };
}
