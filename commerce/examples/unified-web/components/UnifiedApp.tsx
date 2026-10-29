// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/**
 * One app over five: the retail storefront and portal, the travel storefront, and the telecom and
 * ticketing portals, behind one navigation rail. Each hosted app is its own source, imported as it
 * is (its page, its stylesheet confined to its frame by postcss-scope.cjs, its typefaces, its
 * Chinese table), and talks to its own vertical's API. An app mounts the first time it is opened
 * and stays mounted while another is shown, so its session, chat, and cart survive switching.
 */

import dynamic from "next/dynamic";
import { type ComponentType, useCallback, useEffect, useState } from "react";
import { Icon, type IconName, PortalHostContext } from "web-shared";
import { LocaleProvider, type Messages, useLocale } from "web-shared/i18n";
import type { Locale } from "web-shared/locale";

import "../../retail/storefront-web/app/globals.css";
import "../../retail/merchant-web/app/globals.css";
import "../../travel/storefront-web/app/globals.css";
import "../../telecom/merchant-web/app/globals.css";
import "../../entertainment/merchant-web/app/globals.css";
import { fontVariables as retailStoreFonts } from "../../retail/storefront-web/app/fonts";
import { fontVariables as retailPortalFonts } from "../../retail/merchant-web/app/fonts";
import { fontVariables as travelStoreFonts } from "../../travel/storefront-web/app/fonts";
import { fontVariables as telecomPortalFonts } from "../../telecom/merchant-web/app/fonts";
import { fontVariables as ticketsPortalFonts } from "../../entertainment/merchant-web/app/fonts";
import { ZH as retailStoreZh } from "../../retail/storefront-web/lib/i18n-zh";
import { ZH as retailPortalZh } from "../../retail/merchant-web/lib/i18n-zh";
import { ZH as travelStoreZh } from "../../travel/storefront-web/lib/i18n-zh";
import { ZH as telecomPortalZh } from "../../telecom/merchant-web/lib/i18n-zh";
import { ZH as ticketsPortalZh } from "../../entertainment/merchant-web/lib/i18n-zh";

interface HostedApp {
  id: string;
  scope: string; // hosted-apps.cjs
  icon: IconName;
  vertical: Record<Locale, string>;
  surface: Record<Locale, string>;
  fonts: string;
  messages: Messages;
  Page: ComponentType;
}

const page = (load: () => Promise<{ default: ComponentType }>) => dynamic(load, { ssr: false });

const APPS: HostedApp[] = [
  {
    id: "retail-store",
    scope: "u-retail-store",
    icon: "bag",
    vertical: { zh: "零售", en: "Retail" },
    surface: { zh: "店铺", en: "Store" },
    fonts: retailStoreFonts,
    messages: retailStoreZh,
    Page: page(() => import("../../retail/storefront-web/app/page")),
  },
  {
    id: "retail-portal",
    scope: "u-retail-portal",
    icon: "chart",
    vertical: { zh: "零售", en: "Retail" },
    surface: { zh: "商家门户", en: "Portal" },
    fonts: retailPortalFonts,
    messages: retailPortalZh,
    Page: page(() => import("../../retail/merchant-web/app/page")),
  },
  {
    id: "travel-store",
    scope: "u-travel-store",
    icon: "plane",
    vertical: { zh: "旅行", en: "Travel" },
    surface: { zh: "店铺", en: "Store" },
    fonts: travelStoreFonts,
    messages: travelStoreZh,
    Page: page(() => import("../../travel/storefront-web/app/page")),
  },
  {
    id: "telecom-portal",
    scope: "u-telecom-portal",
    icon: "signal",
    vertical: { zh: "电信", en: "Telecom" },
    surface: { zh: "商家门户", en: "Portal" },
    fonts: telecomPortalFonts,
    messages: telecomPortalZh,
    Page: page(() => import("../../telecom/merchant-web/app/page")),
  },
  {
    id: "tickets-portal",
    scope: "u-tickets-portal",
    icon: "ticket",
    vertical: { zh: "票务", en: "Tickets" },
    surface: { zh: "商家门户", en: "Portal" },
    fonts: ticketsPortalFonts,
    messages: ticketsPortalZh,
    Page: page(() => import("../../entertainment/merchant-web/app/page")),
  },
];

const RAIL_ZH: Messages = { "ACME commerce": "ACME 商业演示", Apps: "应用" };

/** One hosted app in its frame: the scope class its styles live under, its typefaces, its own
 * Chinese table, and the element its sheets render into. */
function Frame({ app, active, locale }: { app: HostedApp; active: boolean; locale: Locale }) {
  const [host, setHost] = useState<HTMLElement | null>(null);
  return (
    <div
      ref={setHost}
      data-portal-host
      className={`unified-frame ${app.scope} ${app.fonts}`}
      hidden={!active}
      aria-hidden={!active}
    >
      <PortalHostContext.Provider value={host}>
        <LocaleProvider initial={locale} messages={app.messages}>
          <app.Page />
        </LocaleProvider>
      </PortalHostContext.Provider>
    </div>
  );
}

function Rail({ current, onOpen }: { current: string; onOpen: (id: string) => void }) {
  const { locale, t } = useLocale();
  return (
    <nav className="unified-rail" aria-label={t("Apps")}>
      <div className="unified-mark" title={t("ACME commerce")}>
        A
      </div>
      {APPS.map((app) => (
        <button
          key={app.id}
          type="button"
          className="unified-tab"
          aria-current={app.id === current ? "page" : undefined}
          onClick={() => onOpen(app.id)}
          title={`${app.vertical[locale]} · ${app.surface[locale]}`}
        >
          <Icon name={app.icon} size={19} />
          <span className="unified-tab-vertical">{app.vertical[locale]}</span>
          <span className="unified-tab-surface">{app.surface[locale]}</span>
        </button>
      ))}
    </nav>
  );
}

export default function UnifiedApp({ initialLocale }: { initialLocale: Locale }) {
  const [current, setCurrent] = useState(APPS[0].id);
  const [opened, setOpened] = useState<Set<string>>(() => new Set([APPS[0].id]));

  const open = useCallback((id: string) => {
    setCurrent(id);
    setOpened((seen) => (seen.has(id) ? seen : new Set(seen).add(id)));
    const url = new URL(window.location.href);
    url.searchParams.set("app", id);
    window.history.replaceState(null, "", url);
  }, []);

  // The app named in the URL (?app=retail-portal), so a link or a reload lands on it.
  useEffect(() => {
    const named = new URLSearchParams(window.location.search).get("app");
    if (named && APPS.some((app) => app.id === named)) open(named);
  }, [open]);

  return (
    <LocaleProvider initial={initialLocale} messages={RAIL_ZH}>
      <div className="unified">
        <Rail current={current} onOpen={open} />
        <main className="unified-stage">
          {APPS.filter((app) => opened.has(app.id)).map((app) => (
            <Frame key={app.id} app={app} active={app.id === current} locale={initialLocale} />
          ))}
        </main>
      </div>
    </LocaleProvider>
  );
}
