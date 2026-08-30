/** Bilingual synonym map. expand(token) returns the token plus equivalents. */

const GROUPS: string[][] = [
  ['godown', 'warehouse', 'store', 'stock location', 'gudam', 'store room'],
  ['bill', 'invoice', 'invioce', 'invoce'],
  ['gstin', 'gstn', 'gst number', 'gst no'],
  ['complete', 'final', 'done', 'mark done'],
  ['stock', 'maal', 'inventory', 'qty'],
  ['customer', 'party', 'client'],
  ['receipt', 'payment in', 'collection', 'recieve', 'receive'],
  ['allocate', 'match', 'apply', 'adjust'],
  ['carton', 'box', 'peti', 'case'],
  ['piece', 'pieces', 'pcs', 'pc'],
  ['create', 'add', 'ban', 'banao', 'banana'],
  ['cannot', 'cant', "can't", 'nahi', 'nahi ban raha', "can't create", 'sakta nahi'],
  ['cancel', 'delete', 'void', 'undo', 'credit note'],
  ['unit', 'units', 'uom', 'unit of measure'],
  ['how', 'kaise', 'kese'],
  ['why', 'kyu', 'kyun', 'kyo'],
  ['what', 'kya'],
  ['where', 'kaha', 'kahaan'],
  ['open', 'khol', 'kholo', 'kholna'],
  ['share', 'whatsapp', 'pdf', 'send'],
  ['blocked', 'band', 'inactive', 'stop'],
  ['owner', 'maalik', 'boss', 'admin'],
  ['purchase', 'khareed', 'kharid', 'supplier bill'],
  ['journal', 'journals', 'ledger entry'],
  ['offline', 'outbox', 'queued'],
  ['ended', 'over', 'khatam', 'expired'],
  ['locked', 'read only', 'readonly', 'paused'],
];

const INDEX = new Map<string, Set<string>>();
for (const group of GROUPS) {
  const set = new Set(group.map((w) => w.toLowerCase()));
  for (const word of set) {
    const existing = INDEX.get(word) ?? new Set<string>();
    for (const other of set) existing.add(other);
    INDEX.set(word, existing);
  }
}

export function expand(token: string): Set<string> {
  const key = token.trim().toLowerCase();
  if (!key) return new Set();
  const out = new Set<string>([key]);
  const hit = INDEX.get(key);
  if (hit) {
    for (const w of hit) out.add(w);
  }
  // Multi-word group keys: "nahi ban raha"
  if (key.includes(' ')) {
    for (const [k, vals] of INDEX) {
      if (k.includes(key) || key.includes(k)) {
        for (const w of vals) out.add(w);
      }
    }
  }
  return out;
}

export function expandAll(tokens: string[]): Set<string> {
  const out = new Set<string>();
  for (const token of tokens) {
    for (const w of expand(token)) out.add(w);
  }
  return out;
}

/** Phrase keys in the index (space-containing), longest first. */
export function multiWordSynonymKeys(): string[] {
  return [...INDEX.keys()].filter((k) => k.includes(' ')).sort((a, b) => b.length - a.length);
}
