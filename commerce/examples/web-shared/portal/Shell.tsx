// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import type { AgentApi } from "../api";
import { LanguageToggle, useT } from "../i18n";
import { ModelSettingsButton } from "../ModelSettings";
import { Icon, type IconName } from "../icons";
import { Avatar } from "../ui";

export interface PortalNavItem<V extends string> {
  id: V;
  label: string;
  icon: IconName;
  /** A plain count shown beside the label. */
  count?: number | null;
  /** A count that needs the operator; tinted. */
  attention?: number | null;
}

interface PortalBrand {
  /** The store's mark: a small tile the vertical draws itself. */
  mark: ReactNode;
  name: string;
  detail: string;
}

/**
 * The merchant portals' frame: a sidebar with the store, the views, the assistant entry and the
 * signed-in operator; the page; and the assistant rail beside it. Below `lg` the sidebar becomes a
 * top bar with tabs. Every color comes from the app's tokens; a vertical that draws on the page
 * ground targets `.portal-main`.
 */
export function PortalShell<V extends string>({
  brand,
  nav,
  view,
  onViewChange,
  operator,
  assistantOpen,
  assistantBusy = false,
  onToggleAssistant,
  rail,
  children,
  api,
}: {
  brand: PortalBrand;
  nav: PortalNavItem<V>[];
  view: V;
  onViewChange: (view: V) => void;
  operator: { name: string; role: string };
  assistantOpen: boolean;
  assistantBusy?: boolean;
  onToggleAssistant: () => void;
  rail: ReactNode;
  children: ReactNode;
  /** The portal's API client; the model settings panel calls its root. */
  api: AgentApi;
}) {
  const t = useT();
  return (
    <div className="flex h-dvh bg-(--ground) text-(--ink)">
      <aside className="hidden w-16 shrink-0 flex-col border-r border-(--line) bg-(--chrome) px-2 py-3.5 lg:flex xl:w-[220px] xl:px-3">
        <div className="flex items-center gap-2.5 px-1 pb-4 xl:px-2">
          {brand.mark}
          <div className="hidden min-w-0 xl:block">
            <div className="truncate text-[14px] font-semibold leading-tight">{brand.name}</div>
            <div className="truncate text-[12px] text-(--ink-soft)">{brand.detail}</div>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5" aria-label={t("Portal views")}>
          {nav.map((item) => {
            const active = item.id === view;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onViewChange(item.id)}
                aria-current={active ? "page" : undefined}
                aria-label={item.label}
                title={item.label}
                className={`relative flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-left text-[14px] transition-colors ${
                  active
                    ? "bg-(--well) font-semibold text-(--ink)"
                    : "font-medium text-(--ink-2) hover:bg-(--ground)"
                }`}
              >
                <Icon name={item.icon} className={active ? "text-(--ink)" : "text-(--ink-soft)"} />
                <span className="hidden min-w-0 flex-1 truncate xl:block">{item.label}</span>
                {item.attention ? (
                  <span className="absolute right-1 top-1 rounded-full bg-(--danger-soft) px-1.5 text-[11px] font-semibold text-(--danger) xl:static">
                    {item.attention}
                  </span>
                ) : item.count != null ? (
                  <span className="hidden text-[12px] tabular-nums text-(--ink-soft) xl:inline">{item.count}</span>
                ) : null}
              </button>
            );
          })}
        </nav>
        <button
          type="button"
          onClick={onToggleAssistant}
          aria-pressed={assistantOpen}
          aria-label={assistantOpen ? t("Hide assistant") : t("Show assistant")}
          title={assistantOpen ? t("Hide assistant") : t("Show assistant")}
          className={`mt-3 flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-left text-[14px] font-semibold transition-colors ${
            assistantOpen
              ? "bg-(--accent-soft) text-(--accent-ink)"
              : "text-(--ink-2) hover:bg-(--ground)"
          }`}
        >
          <Icon name="spark" className="text-(--accent)" />
          <span className="hidden flex-1 xl:block">{t("Assistant")}</span>
          {assistantBusy ? (
            <span className="relative hidden h-2 w-2 xl:flex" aria-label={t("Working")}>
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-(--accent) opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-(--accent)" />
            </span>
          ) : assistantOpen ? (
            <span className="hidden h-[7px] w-[7px] rounded-full bg-(--accent) shadow-[0_0_0_3px_var(--accent-soft)] xl:block" aria-hidden />
          ) : null}
        </button>
        <div className="mb-3 mt-auto flex flex-col items-center gap-2 xl:ml-2 xl:flex-row">
          <LanguageToggle />
          <ModelSettingsButton api={api} />
        </div>
        <div className="flex items-center gap-2.5 border-t border-(--line) px-1 pt-3 xl:px-2">
          <Avatar name={operator.name} />
          <div className="hidden min-w-0 xl:block">
            <div className="truncate text-[13px] font-semibold leading-tight">{operator.name}</div>
            <div className="truncate text-[11.5px] text-(--ink-soft)">{operator.role}</div>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-(--line) bg-(--chrome) px-3 py-2 lg:hidden">
          {brand.mark}
          <nav className="panel-scroll flex min-w-0 flex-1 gap-1 overflow-x-auto" aria-label={t("Portal views")}>
            {nav.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onViewChange(item.id)}
                aria-current={item.id === view ? "page" : undefined}
                className={`flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium ${
                  item.id === view ? "bg-(--well) text-(--ink)" : "text-(--ink-soft)"
                }`}
              >
                {item.label}
                {item.attention ? (
                  <span className="rounded-full bg-(--danger-soft) px-1.5 text-[10.5px] font-semibold text-(--danger)">{item.attention}</span>
                ) : null}
              </button>
            ))}
          </nav>
          <ModelSettingsButton api={api} />
          <LanguageToggle />
          <button
            type="button"
            onClick={onToggleAssistant}
            aria-pressed={assistantOpen}
            className={`flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-semibold ${
              assistantOpen ? "bg-(--accent-soft) text-(--accent-ink)" : "bg-(--ink) text-(--surface)"
            }`}
          >
            <Icon name="spark" size={15} />
            {t("Assistant")}
          </button>
        </header>

        <div className="flex min-h-0 flex-1">
          <main className="portal-main panel-scroll min-w-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-5 sm:px-7 sm:py-6">{children}</div>
          </main>
          {rail}
        </div>
      </div>
    </div>
  );
}
