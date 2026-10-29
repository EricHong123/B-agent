// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { type ButtonHTMLAttributes, createContext, type ReactNode, useContext, useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { formatChangePct } from "./format";
import { useT } from "./i18n";
import { Icon, type IconName } from "./icons";

/**
 * Where sheets render. A page that hosts several apps (examples/unified-web) provides each app's
 * own element, so a sheet stays inside that app's styles; an app on its own renders into the body.
 */
export const PortalHostContext = createContext<HTMLElement | null>(null);

export type Tone = "ok" | "warn" | "danger" | "info" | "violet" | "accent" | "muted";

/** How a kind of record shows in rows and digests. */
export interface KindStyle {
  label: string;
  icon: IconName;
  tone: Tone;
}

const TONE_SOFT: Record<Tone, string> = {
  ok: "bg-(--ok-soft) text-(--ok)",
  warn: "bg-(--warn-soft) text-(--warn)",
  danger: "bg-(--danger-soft) text-(--danger)",
  info: "bg-(--info-soft) text-(--info)",
  violet: "bg-(--violet-soft) text-(--violet)",
  accent: "bg-(--accent-soft) text-(--accent-ink)",
  muted: "bg-(--well) text-(--ink-soft)",
};

/** A status or label chip; `dot` marks a state rather than a category. */
export function Pill({ tone = "muted", dot = false, children, title }: { tone?: Tone; dot?: boolean; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11.5px] font-semibold leading-[1.35] ${TONE_SOFT[tone]}`}
    >
      {dot ? <i aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" /> : null}
      {children}
    </span>
  );
}

export function ChangeChip({ changePct }: { changePct: number | null | undefined }) {
  if (changePct == null) return null;
  return <Pill tone={changePct >= 0 ? "ok" : "danger"}>{formatChangePct(changePct)}</Pill>;
}

/** The tinted roundel that says what kind of thing a row is. */
export function KindIcon({ icon, tone = "muted", size = 36 }: { icon: IconName; tone?: Tone; size?: number }) {
  return (
    <span
      aria-hidden
      className={`grid shrink-0 place-items-center ${TONE_SOFT[tone]}`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.3) }}
    >
      <Icon name={icon} size={Math.round(size * 0.53)} />
    </span>
  );
}

/** A record's image, or the placeholder tile when it has none. */
export function Thumb({ src, alt = "", size = 40, className = "" }: { src?: string | null; alt?: string; size?: number; className?: string }) {
  return (
    <span
      className={`grid shrink-0 place-items-center overflow-hidden bg-(--well) text-(--ink-faint) ${className}`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.22) }}
    >
      {src ? (
        <img src={src} alt={alt} width={size} height={size} className="h-full w-full object-cover" />
      ) : (
        <Icon name="photo" size={Math.round(size * 0.42)} />
      )}
    </span>
  );
}

/** Initials in a roundel, for the signed-in person. */
export function Avatar({ name }: { name: string }) {
  const initials = name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span
      aria-hidden
      className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-(--well) text-[12px] font-semibold text-(--ink) shadow-[inset_0_0_0_1px_var(--line)]"
    >
      {initials}
    </span>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
      <div className="min-w-0 flex-1">
        <h1 className="page-title text-[24px] font-semibold leading-tight tracking-[-0.02em] text-(--ink)">{title}</h1>
        {subtitle ? <p className="mt-1 text-[13.5px] leading-snug text-(--ink-soft)">{subtitle}</p> : null}
      </div>
      {children ? <div className="flex shrink-0 flex-wrap items-center gap-2">{children}</div> : null}
    </div>
  );
}

/** A card with an optional header row. */
export function Panel({
  title,
  subtitle,
  action,
  icon,
  children,
  bodyClassName = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  children: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <section className="rounded-2xl border border-(--line) bg-(--card) shadow-(--shadow-sm)">
      {title ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-[18px] pb-1.5 pt-3.5">
          {icon}
          <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-(--ink)">{title}</h2>
          {subtitle ? <span className="text-[12.5px] text-(--ink-soft)">{subtitle}</span> : null}
          {action ? <div className="ml-auto flex items-center gap-2">{action}</div> : null}
        </div>
      ) : null}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export interface SegmentOption<T extends string> {
  id: T;
  label: string;
  count?: number | null;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex gap-0.5 rounded-[9px] bg-(--ground) p-[3px] text-[12.5px]">
      {options.map((option) => {
        const on = option.id === value;
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(option.id)}
            className={`rounded-[7px] px-2.5 py-1 transition-colors ${
              on ? "bg-(--card) font-semibold text-(--ink) shadow-(--shadow-sm)" : "font-medium text-(--ink-soft) hover:text-(--ink)"
            }`}
          >
            {option.label}
            {option.count != null ? <span className="ml-1 font-medium tabular-nums text-(--ink-faint)">{option.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/** Area sparkline with the endpoint marked; `prior` draws the comparison period dashed. */
export function Sparkline({
  points,
  prior,
  height = 46,
  label,
  className = "",
}: {
  points: number[];
  prior?: number[] | null;
  height?: number;
  label: string;
  className?: string;
}) {
  const gradientId = useId();
  if (points.length < 2) return null;
  const width = 200;
  const pad = 4;
  const all = prior?.length ? points.concat(prior) : points;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const place = (series: number[]) =>
    series.map((value, index) => [
      pad + (index * (width - 2 * pad)) / (series.length - 1),
      height - pad - ((value - min) / span) * (height - 2 * pad - 6) - 3,
    ]);
  const line = (coords: number[][]) => `M${coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L")}`;
  const coords = place(points);
  const [endX, endY] = coords[coords.length - 1];
  const path = line(coords);
  return (
    <div className={`relative ${className}`} style={{ height }} role="img" aria-label={label}>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--ink)" stopOpacity=".14" />
            <stop offset="1" stopColor="var(--ink)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" x2={width} y1={height - 0.5} y2={height - 0.5} stroke="var(--line)" vectorEffect="non-scaling-stroke" />
        {prior && prior.length > 1 ? (
          <path d={line(place(prior))} fill="none" stroke="var(--ink-faint)" strokeWidth="1.3" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        ) : null}
        <path d={`${path} L${endX},${height} L${coords[0][0]},${height} Z`} fill={`url(#${gradientId})`} />
        <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <span
        aria-hidden
        className="absolute h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.6px] border-(--ink) bg-(--card)"
        style={{ left: `${(endX / width) * 100}%`, top: `${(endY / height) * 100}%` }}
      />
    </div>
  );
}

/** One figure in the KPI strip; clicking it prefills a question for the assistant. */
export function StatTile({
  label,
  value,
  changePct,
  points,
  prior,
  onClick,
  ariaLabel,
}: {
  label: string;
  value: string;
  changePct?: number | null;
  points?: number[];
  prior?: number[] | null;
  onClick?: () => void;
  ariaLabel?: string;
}) {
  const t = useT();
  const body = (
    <>
      <div className="relative text-[12.5px] font-medium whitespace-nowrap text-(--ink-soft)">
        {label}
        {onClick ? (
          <span className="absolute right-0 top-0 flex items-center gap-1 bg-inherit text-[11.5px] text-(--ink-faint) opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
            {t("Ask why")} <Icon name="arrow-right" size={12} />
          </span>
        ) : null}
      </div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className="text-[26px] font-semibold leading-none tracking-[-0.02em] tabular-nums text-(--ink)">{value}</span>
        <ChangeChip changePct={changePct} />
      </div>
      {points && points.length > 1 ? <Sparkline points={points} prior={prior} label={t("{label} over the period", { label })} className="mt-2" /> : null}
    </>
  );
  const className = "group block w-full px-[18px] pb-3.5 pt-4 text-left transition-colors";
  return onClick ? (
    <button type="button" onClick={onClick} aria-label={ariaLabel} className={`${className} hover:bg-(--ground)/60 focus-visible:bg-(--ground)/60 focus-visible:outline-none`}>
      {body}
    </button>
  ) : (
    <div className={className}>{body}</div>
  );
}

/** Lays StatTiles out as one card with hairline dividers. */
export function StatStrip({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 [&>*]:border-(--line) max-xl:[&>*:nth-child(even)]:border-l max-xl:[&>*:nth-child(n+3)]:border-t xl:[&>*+*]:border-l">
      {children}
    </div>
  );
}

/** The small hand-off button on rows and cards: a portal prefills the assistant with it, a storefront sends. */
export function AskButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border border-(--line-strong) bg-(--card) px-2.5 py-[5px] text-[12px] font-semibold text-(--ink-2) transition-colors hover:border-(--accent) hover:bg-(--accent-soft) hover:text-(--accent-ink)"
    >
      <Icon name="spark" size={13} className="text-(--accent)" />
      {label}
    </button>
  );
}

export function SearchField({
  value,
  onChange,
  placeholder,
  label,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label: string;
  className?: string;
}) {
  return (
    <label className={`flex items-center gap-2 rounded-[10px] border border-(--line-strong) bg-(--card) px-3 py-[7px] text-(--ink-soft) shadow-(--shadow-sm) focus-within:border-(--accent) ${className}`}>
      <Icon name="search" size={17} />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="min-w-0 flex-1 bg-transparent text-[14px] text-(--ink) outline-none placeholder:text-(--ink-faint)"
      />
    </label>
  );
}

/** One figure in a facts strip: `<div className="grid grid-cols-4 divide-x ...">`. */
export function Fact({ label, value, tone }: { label: string; value: ReactNode; tone?: "warn" | "danger" }) {
  return (
    <div className="min-w-0 px-2.5 py-2.5">
      <div className="text-[11.5px] font-medium leading-tight text-(--ink-soft)">{label}</div>
      <div className={`mt-0.5 truncate text-[17px] font-semibold tabular-nums tracking-[-0.01em] ${tone === "danger" ? "text-(--danger)" : tone === "warn" ? "text-(--warn)" : "text-(--ink)"}`}>
        {value ?? "—"}
      </div>
    </div>
  );
}

export function Facts({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-4 divide-x divide-(--line) overflow-hidden rounded-[14px] border border-(--line)">{children}</div>;
}

/** A section heading inside a sheet, with an optional note on the right. */
export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <h3 className="mb-2 flex items-baseline gap-2 text-[13px] font-semibold text-(--ink)">
      {children}
      {aside ? <span className="ml-auto text-[12px] font-normal text-(--ink-soft)">{aside}</span> : null}
    </h3>
  );
}

/** A short horizontal bar for a 0–1 share; `tone` picks the fill token. */
export function MiniBar({ value, tone = "muted", className = "w-14" }: { value: number; tone?: Tone; className?: string }) {
  const fill: Record<Tone, string> = {
    ok: "bg-(--ok)",
    warn: "bg-(--warn)",
    danger: "bg-(--danger)",
    info: "bg-(--info)",
    violet: "bg-(--violet)",
    accent: "bg-(--accent)",
    muted: "bg-(--ink-soft)",
  };
  const pct = Math.max(4, Math.min(100, value * 100));
  return (
    <span className={`relative inline-block h-[5px] overflow-hidden rounded-full bg-(--well) ${className}`} aria-hidden>
      <span className={`absolute inset-y-0 left-0 rounded-full ${fill[tone]}`} style={{ width: `${pct}%` }} />
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`ac-skeleton rounded-2xl ${className}`} />;
}

/** The empty or unreachable state inside a view. */
export function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-(--line) bg-(--card) p-6 text-[14px] leading-relaxed text-(--ink-soft)">{children}</div>;
}

/** A right-hand sheet over a scrim, portalled to the body; Escape and the scrim close it. */
export function Sheet({
  title,
  detail,
  onClose,
  footer,
  children,
  closeLabel,
}: {
  title: ReactNode;
  detail?: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
  closeLabel?: string;
}) {
  const t = useT();
  const [host, setHost] = useState<HTMLElement | null>(null);
  const scopedHost = useContext(PortalHostContext);
  const titleId = useId();
  useEffect(() => {
    setHost(scopedHost ?? document.body);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, scopedHost]);
  if (!host) return null;
  return createPortal(
    <>
      <div onClick={onClose} aria-hidden className="fixed inset-0 z-40 bg-black/30" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="ac-slide-in-right fixed inset-y-0 right-0 z-50 flex w-[min(96vw,468px)] flex-col overflow-hidden bg-(--card) shadow-(--shadow-lg) sm:inset-y-2.5 sm:right-2.5 sm:rounded-[18px]"
      >
        <div className="flex items-center gap-2 border-b border-(--line) py-3 pl-[18px] pr-3">
          <div id={titleId} className="min-w-0 flex-1 truncate text-[14px] font-semibold text-(--ink)">
            {title}
            {detail ? <span className="ml-2 font-normal tabular-nums text-(--ink-soft)">{detail}</span> : null}
          </div>
          <IconButton icon="x" label={closeLabel ?? t("Close")} onClick={onClose} />
        </div>
        <div className="panel-scroll flex flex-1 flex-col gap-4 overflow-y-auto p-[18px]">{children}</div>
        {footer ? <div className="flex items-center gap-2 border-t border-(--line) px-[18px] py-3">{footer}</div> : null}
      </aside>
    </>,
    host,
  );
}

export function IconButton({ icon, label, onClick, className = "" }: { icon: IconName; label: string; onClick: () => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg text-(--ink-soft) transition-colors hover:bg-(--ground) hover:text-(--ink) ${className}`}
    >
      <Icon name={icon} size={17} />
    </button>
  );
}

/** `primary` is the ink button; `accent` is reserved for approvals. */
export function Button({
  variant = "secondary",
  size = "md",
  icon,
  children,
  className = "",
  ...rest
}: {
  variant?: "primary" | "secondary" | "accent";
  size?: "sm" | "md";
  icon?: IconName;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const variants = {
    primary: "bg-(--ink) text-(--surface) shadow-(--shadow-sm) hover:brightness-110",
    secondary: "border border-(--line-strong) bg-(--card) text-(--ink) hover:bg-(--ground)",
    accent: "bg-(--accent-strong) text-(--on-accent) shadow-(--shadow-sm) hover:brightness-95",
  };
  const sizes = { sm: "px-3 py-[6px] text-[13px] rounded-[9px]", md: "px-3.5 py-2 text-[13.5px] rounded-[10px]" };
  return (
    <button
      type="button"
      className={`inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap font-semibold transition disabled:opacity-50 ${variants[variant]} ${sizes[size]} ${className}`}
      {...rest}
    >
      {icon ? <Icon name={icon} size={size === "sm" ? 15 : 16} /> : null}
      {children}
    </button>
  );
}
