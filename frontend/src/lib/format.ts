export function displayValue(value: number | string | boolean | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return String(value);
}

export function displayPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (Number.isInteger(n)) return `${n}%`;
  return `${n.toFixed(2)}%`;
}

export function displaySeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(2)}s`;
}

export function videoLabel(path: string | undefined): string {
  if (!path) return "Unknown video";
  const normalized = path.replaceAll("\\", "/");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || normalized;
}

export function playerLabel(stableId: number, names?: Record<string, string>): string {
  return names?.[String(stableId)] || `Player ${stableId}`;
}

export function formatClock(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function boolLabel(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value ? "Yes" : "No";
}
