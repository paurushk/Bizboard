export function expiryTone(iso?: string | null): 'error' | 'warning' | 'success' | null {
  if (!iso) return null;
  const end = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(end.getTime())) return null;
  const days = Math.ceil((end.getTime() - Date.now()) / 86_400_000);
  if (days < 15) return 'error';
  if (days <= 60) return 'warning';
  return 'success';
}
