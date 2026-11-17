export function money(value: string | null | undefined, currency?: string | null): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  const text = Number.isFinite(n)
    ? n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : value;
  return currency ? `${currency} ${text}` : text;
}

export function percent(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function humanize(code: string): string {
  return code.replace(/[_:]+/g, " ").toLowerCase();
}
