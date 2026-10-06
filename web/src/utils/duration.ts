/** Human duration for a number of seconds: "45 min", "3 h", "2 d 3 h". Null or negative gives "—". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 60) return '< 1 min';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rest = minutes % 60;
    return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours === 0 ? `${days} d` : `${days} d ${restHours} h`;
}
