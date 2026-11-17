export function money(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return Number.isFinite(n)
    ? n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : value;
}

export function qty(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return String(Number(value));
}

export function percent(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** How long something has waited, in the largest sensible unit. */
export function age(iso: string, now = Date.now()): string {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}

export function humanize(code: string): string {
  return code.replace(/[_.:]+/g, " ").toLowerCase();
}
