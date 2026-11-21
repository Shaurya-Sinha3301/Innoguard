/** Design-system primitives for the module mosaic. Every style uses the tokens in index.css. */
import { AlertTriangle, ChevronRight, Inbox, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";
import { reasonInfo } from "../reasons";

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* ---------- Module: the one container. A ruled box with a small header tab. ---------- */

type ModuleProps = {
  title: string;
  icon?: LucideIcon;
  count?: number;
  alert?: boolean;
  action?: { to: string; label: string };
  extra?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
  id?: string;
};

export function IconTile({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line bg-fill text-ink-2">
      <Icon className="h-4 w-4" />
    </span>
  );
}

export function Module({ title, icon, count, alert, action, extra, className, bodyClassName, children, id }: ModuleProps) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section aria-labelledby={headingId} className={cx("min-w-0 overflow-hidden rounded-xl border border-line bg-surface", className)}>
      <header className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        {icon && <IconTile icon={icon} />}
        <h2 id={headingId} className="font-display text-md font-semibold tracking-tight">
          {title}
        </h2>
        {count !== undefined && (
          <span
            className={cx(
              "rounded-full px-2 font-mono text-xs font-semibold",
              alert && count > 0 ? "bg-red text-bg" : "bg-fill text-ink-2",
            )}
          >
            {count}
          </span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {extra}
          {action && (
            <Link to={action.to} className="inline-flex items-center text-xs text-ink-2 hover:text-ink hover:underline">
              {action.label}
              <ChevronRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>
      </header>
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/* ---------- Chip: a reference code, like INV-10042, in the accent colour ---------- */

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex whitespace-nowrap rounded-md bg-accent px-1.5 py-0.5 font-mono text-[13px] font-semibold text-accent-ink",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ---------- Segmented bar: a row of equal ticks, filled in proportion ---------- */

export function SegmentedBar({
  value,
  total,
  ticks = 24,
  label,
  tone = "bg-accent",
}: {
  value: number;
  total: number;
  ticks?: number;
  label: string;
  tone?: string;
}) {
  const filled = total > 0 ? Math.round((value / total) * ticks) : 0;
  return (
    <div role="img" aria-label={label} className="flex gap-[3px]">
      {Array.from({ length: ticks }, (_, i) => (
        <span key={i} className={cx("h-8 flex-1 rounded-[3px]", i < filled ? tone : "bg-fill")} />
      ))}
    </div>
  );
}

/* ---------- Buttons ---------- */

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "md" | "lg";

const buttonStyles: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink hover:brightness-95",
  secondary: "border border-line bg-surface text-ink hover:bg-fill",
  danger: "border border-red/50 bg-surface text-red hover:bg-red-tint",
  ghost: "text-ink-2 hover:bg-fill hover:text-ink",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 font-semibold transition-colors",
        size === "lg" ? "h-12 rounded-xl px-5 text-md" : "h-9 rounded-lg px-3.5 text-sm",
        "disabled:cursor-not-allowed disabled:opacity-45",
        buttonStyles[variant],
        className,
      )}
      {...props}
    />
  );
}

/* ---------- Status: one fixed legend, the same on every screen ---------- */

const STATUS: Record<string, { label: string; tone: string }> = {
  NEEDS_REVIEW: { label: "Needs review", tone: "bg-red text-bg" },
  AUTO_APPROVED: { label: "Auto-approved", tone: "bg-green-tint text-green" },
  APPROVED: { label: "Approved", tone: "bg-green-tint text-green" },
  POSTED: { label: "Posted", tone: "bg-green text-bg" },
  REJECTED: { label: "Rejected", tone: "bg-fill text-ink-2 ring-1 ring-inset ring-line" },
  FAILED: { label: "Failed", tone: "bg-red-tint text-red ring-1 ring-inset ring-red/40" },
  POSTING: { label: "Posting", tone: "bg-fill text-ink-2" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: status.replace(/_/g, " ").toLowerCase(), tone: "bg-fill text-ink-2" };
  return (
    <span className={cx("inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold", s.tone)}>
      {s.label}
    </span>
  );
}

export function ReasonTag({ code, title }: { code: string; title?: boolean }) {
  const info = reasonInfo(code);
  return (
    <span
      title={title ? info.explain : undefined}
      className="inline-flex whitespace-nowrap rounded-full bg-red-tint px-2 py-0.5 text-xs font-medium text-red"
    >
      {info.label}
    </span>
  );
}

/* ---------- States ---------- */

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 px-4 py-8 text-center">
      <Inbox aria-hidden className="h-5 w-5 text-ink-3" />
      <p className="text-sm font-semibold">{title}</p>
      {children && <p className="max-w-sm text-sm text-ink-2">{children}</p>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="flex items-start gap-2 rounded-lg border border-red/40 bg-red-tint px-3 py-2 text-sm text-red">
      <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </p>
  );
}

export function SkeletonRows({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" className="divide-y divide-line">
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="flex gap-4 px-3 py-2.5">
          {Array.from({ length: cols }, (_, c) => (
            <span key={c} className="h-3 flex-1 animate-pulse rounded-sm bg-fill" />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ---------- Tables ---------- */

export function Table({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto">
      <table aria-label={label} className="w-full border-collapse text-sm">
        {children}
      </table>
    </div>
  );
}

export const th =
  "label-mono whitespace-nowrap border-b border-line bg-fill-2 px-4 py-2 text-left font-medium";
export const td = "whitespace-nowrap border-b border-line/70 px-4 py-2.5 align-middle";
export const num = "text-right font-mono text-[13px] tabular-nums";

export function Row({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cx("hover:bg-fill-2", className)} {...props} />;
}

/* ---------- Segmented filter ---------- */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: Array<{ value: T; label: string; count?: number }>;
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={cx(
              "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-medium",
              on ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface text-ink-2 hover:bg-fill",
            )}
          >
            {o.label}
            {o.count !== undefined && <span className="font-mono">{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
