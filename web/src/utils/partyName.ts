/** A party name must contain a letter or digit and must not contain markup. */
export function partyNameError(name: string): string | null {
  const text = name.trim();
  if (!text) return null;
  if (text.includes('<') || text.includes('>') || ![...text].some((ch) => /\p{L}|\p{N}/u.test(ch))) {
    return 'invalid';
  }
  return null;
}
