const ONES = [
  '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
  'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
  'Seventeen', 'Eighteen', 'Nineteen',
];
const TENS = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety'];

function twoDigits(n: number): string {
  if (n < 20) return ONES[n];
  return `${TENS[Math.floor(n / 10)]}${n % 10 ? ` ${ONES[n % 10]}` : ''}`.trim();
}

function threeDigits(n: number): string {
  if (n < 100) return twoDigits(n);
  const hundred = ONES[Math.floor(n / 100)];
  const rest = n % 100;
  return rest ? `${hundred} Hundred ${twoDigits(rest)}` : `${hundred} Hundred`;
}

function moneyToPaise(value: number | string): number {
  const text = String(value ?? '').trim();
  if (!text) return 0;
  const unsigned = text.replace(/^[+-]/, '');
  const [wholeRaw, fracRaw = ''] = unsigned.split('.');
  if (!/^\d*$/.test(wholeRaw) || !/^\d*$/.test(fracRaw)) {
    const n = Number(text);
    if (!Number.isFinite(n)) return 0;
    return Math.round(Math.abs(n) * 100);
  }
  const frac = `${fracRaw}000`.slice(0, 3);
  let paise = Number(wholeRaw || '0') * 100 + Number(frac.slice(0, 2));
  if (Number(frac[2] || '0') >= 5) paise += 1;
  return paise;
}

/** Same Indian rupee words the tax invoice PDF prints. */
export function amountInWords(value: number | string): string {
  const paiseTotal = moneyToPaise(value);
  let rupees = Math.floor(paiseTotal / 100);
  const paise = paiseTotal % 100;
  let words = 'Zero';
  if (rupees > 0) {
    const parts: string[] = [];
    const crore = Math.floor(rupees / 10000000);
    rupees %= 10000000;
    const lakh = Math.floor(rupees / 100000);
    rupees %= 100000;
    const thousand = Math.floor(rupees / 1000);
    rupees %= 1000;
    if (crore) parts.push(`${threeDigits(crore)} Crore`);
    if (lakh) parts.push(`${threeDigits(lakh)} Lakh`);
    if (thousand) parts.push(`${threeDigits(thousand)} Thousand`);
    if (rupees) parts.push(threeDigits(rupees));
    words = parts.join(' ');
  }
  let result = `${words} Rupees`;
  if (paise) result += ` and ${twoDigits(paise)} Paise`;
  return `${result} Only`;
}
