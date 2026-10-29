// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityButton } from "../ActivityButton";
import { LanguageToggle, useLocale } from "../i18n";
import { ModelSettingsButton } from "../ModelSettings";
import type { AgentApi } from "../api";
import { Composer } from "../Composer";
import { Icon, type IconName } from "../icons";
import { Inspector } from "../Inspector";
import { AiLabel } from "../Transcript";
import type { AgentTurn } from "../turn";
import { Avatar } from "../ui";
import { FrameContext } from "./frame";
import { AccountSheet, type Profile } from "./home";

export interface StoreView<V extends string> {
  id: V;
  label: string;
  icon: IconName;
  /** A count that wants the shopper's attention, tinted; announced as "label, attention". */
  attention?: { count: number; label: string } | null;
}

/** The scrolling page under the app bar that a view renders inside. */
export function StorePage({ children }: { children: ReactNode }) {
  return (
    <div className="panel-scroll h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[808px] flex-col gap-4 px-4 pb-10 pt-6 sm:px-6">
        {children}
      </div>
    </div>
  );
}

/**
 * The storefronts' frame: an app bar with the store, its views, Activity, the bag, and the
 * signed-in shopper; the page with the composer docked under it; the bag panel, docked from `xl`
 * and a drawer below; and the two sheets the bar opens (the shopper's, and Activity). Every color
 * comes from the app's tokens.
 */
export function StoreShell<V extends string>({
  brand,
  views,
  view,
  onViewChange,
  chat,
  api,
  assistantName,
  shopper,
  profiles,
  profileId,
  onSwitchProfile,
  bag,
  panel,
  panelOpen,
  onPanelOpenChange,
  placeholder,
  banner,
  children,
}: {
  brand: ReactNode;
  views: StoreView<V>[];
  view: V;
  onViewChange: (view: V) => void;
  chat: AgentTurn;
  api: AgentApi;
  assistantName: string;
  shopper: { name: string; tier?: string };
  /** The demo's profiles, when the vertical has more than one to switch between. */
  profiles?: Profile[];
  profileId?: string;
  onSwitchProfile?: (id: string) => void;
  /** `count` is what the bag holds; `noun` names it ("item", "booking"); `figure` is a running total; `extra` a live badge. */
  bag: { label: string; count: number; noun: string; figure?: string | null; extra?: ReactNode };
  panel: ReactNode;
  panelOpen: boolean;
  onPanelOpenChange: (open: boolean) => void;
  placeholder: string;
  /** A strip between the app bar and the page. */
  banner?: ReactNode;
  children: ReactNode;
}) {
  const { locale, t } = useLocale();
  const [activityOpen, setActivityOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const bagButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const home = views[0].id;
  const { send } = chat;

  const closePanel = useCallback(() => onPanelOpenChange(false), [onPanelOpenChange]);
  /** Every hand-off on the page goes through here: close the drawer, show the conversation, send. */
  const ask = useCallback(
    (message: string) => {
      onPanelOpenChange(false);
      onViewChange(home);
      void send(message);
    },
    [home, onPanelOpenChange, onViewChange, send],
  );
  const frame = useMemo(
    () => ({ chat, assistantName, ask, closePanel }),
    [chat, assistantName, ask, closePanel],
  );

  // The drawer takes focus when it opens, gives it back when it closes, and closes on Escape.
  useEffect(() => {
    if (!panelOpen) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : bagButtonRef.current;
    panelRef.current?.querySelector<HTMLElement>("button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onPanelOpenChange(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [panelOpen, onPanelOpenChange]);

  return (
    <FrameContext.Provider value={frame}>
      <div className="flex h-dvh flex-col text-(--ink)">
        <header className="flex h-[58px] shrink-0 items-center gap-2 border-b border-(--line) bg-(--chrome) px-3 sm:gap-5 sm:px-5">
          <div className="flex shrink-0 items-center">{brand}</div>
          <nav className="flex min-w-0 items-center gap-1" aria-label={t("Views")}>
            {views.map((item) => {
              const active = item.id === view;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onViewChange(item.id)}
                  aria-current={active ? "page" : undefined}
                  aria-label={item.attention ? `${item.label}, ${item.attention.label}` : item.label}
                  className={`flex items-center gap-2 rounded-[9px] px-2.5 py-1.5 text-[14px] transition-colors ${
                    active ? "bg-(--well) font-semibold text-(--ink)" : "font-medium text-(--ink-2) hover:bg-(--well)/60"
                  }`}
                >
                  <Icon name={item.icon} size={17} className={active ? "text-(--ink)" : "text-(--ink-soft)"} />
                  <span className="hidden sm:inline">{item.label}</span>
                  {item.attention ? (
                    <span className="rounded-full bg-(--warn-soft) px-1.5 text-[11px] font-semibold tabular-nums text-(--warn)">
                      {item.attention.count}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <AiLabel compact />
            <ModelSettingsButton api={api} />
            <LanguageToggle />
            <ActivityButton
              streaming={chat.streaming}
              newMemoryCount={chat.newMemoryKeys.size}
              onClick={() => setActivityOpen(true)}
            />
            <button
              ref={bagButtonRef}
              type="button"
              onClick={() => onPanelOpenChange(true)}
              aria-label={t("Open {label}, {count} {noun}", {
                label: bag.label.toLowerCase(),
                count: bag.count,
                // The noun arrives in the page's language; only the English one takes an "s".
                noun: locale === "en" && bag.count !== 1 ? `${bag.noun}s` : bag.noun,
              })}
              className="flex h-[34px] items-center gap-2 rounded-full bg-(--ink) pl-3 pr-1.5 text-[13px] font-semibold text-(--surface) transition hover:brightness-110 xl:hidden"
            >
              <Icon name="bag" size={16} />
              <span className="hidden sm:inline">{bag.label}</span>
              {bag.figure ? <span className="hidden tabular-nums md:inline">· {bag.figure}</span> : null}
              {bag.extra}
              <span
                key={bag.count}
                data-cart-target
                className="ac-pop grid h-[22px] min-w-[22px] place-items-center rounded-full bg-(--surface) px-1 text-[11.5px] font-bold tabular-nums text-(--ink)"
              >
                {bag.count}
              </span>
            </button>
            <button
              type="button"
              onClick={() => setAccountOpen(true)}
              aria-label={t("{name}: profile and memory", { name: shopper.name })}
              className="flex items-center gap-2.5 rounded-full py-0.5 pl-0.5 pr-1 text-left transition-colors hover:bg-(--well)/60 md:pr-3"
            >
              <Avatar name={shopper.name} />
              <span className="hidden min-w-0 md:block">
                <span className="block truncate text-[13px] font-semibold leading-tight">{shopper.name}</span>
                {shopper.tier ? (
                  <span className="block truncate text-[11.5px] leading-tight text-(--ink-soft)">{shopper.tier}</span>
                ) : null}
              </span>
            </button>
          </div>
        </header>
        {banner}

        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <main className="min-h-0 flex-1">{children}</main>
            <div className="relative shrink-0 px-4 pb-4 pt-2 sm:px-6">
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 -top-6 h-6 bg-linear-to-b from-transparent to-(--ground)"
              />
              <Composer
                send={ask}
                ready={chat.ready}
                busy={chat.busy}
                label={t("Message {name}", { name: assistantName })}
                placeholder={placeholder}
                className="mx-auto max-w-[760px]"
              />
            </div>
          </div>

          <div
            onClick={closePanel}
            aria-hidden
            className={`fixed inset-0 z-40 bg-black/35 transition-opacity duration-300 xl:hidden ${
              panelOpen ? "opacity-100" : "pointer-events-none opacity-0"
            }`}
          />
          {/* Closed below xl the drawer is `invisible`: out of the focus order and the accessibility tree. */}
          <aside
            ref={panelRef}
            aria-label={bag.label}
            className={`fixed inset-y-0 right-0 z-50 flex w-[min(92vw,380px)] flex-col border-l border-(--line) bg-(--card) xl:visible xl:static xl:z-auto xl:w-[348px] xl:shrink-0 xl:translate-x-0 xl:shadow-none xl:transition-none ${
              panelOpen
                ? "visible translate-x-0 shadow-2xl [transition:transform_300ms]"
                : "invisible translate-x-full [transition:transform_300ms,visibility_0s_linear_300ms]"
            }`}
          >
            {panel}
          </aside>
        </div>
        {accountOpen ? (
          <AccountSheet
            name={shopper.name}
            detail={shopper.tier}
            api={api}
            profiles={profiles}
            profileId={profileId}
            onSwitchProfile={onSwitchProfile}
            onClose={() => setAccountOpen(false)}
          />
        ) : null}
        {activityOpen ? (
          <Inspector
            turnCount={chat.turnCount}
            streaming={chat.streaming}
            trace={chat.trace}
            memory={chat.memory}
            newMemoryKeys={chat.newMemoryKeys}
            memoryTitle={t("What {name} knows", { name: assistantName })}
            onClose={() => setActivityOpen(false)}
          />
        ) : null}
      </div>
    </FrameContext.Provider>
  );
}
