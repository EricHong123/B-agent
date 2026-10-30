// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { AskButton, MiniBar, Panel, Pill, Skeleton, useStoreFrame, useT } from "web-shared";
import { formatPrice, usageOf } from "@/lib/format";
import type { AccountContext } from "@/lib/types";

export const ASK_PLAN_FIT = "Which plan fits how I use data?";

/** What a profile with no line sees wherever the account would show. */
export const NO_LINE = "No ACME Mobile line on this account yet. Ask ACME Assistant to compare plans, phones, or home fiber.";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 border-t border-(--line) py-2 first:border-t-0">
      <span className="am-meta w-16 shrink-0">{label}</span>
      <div className="min-w-0 flex-1 text-[13.5px] text-(--ink)">{children}</div>
    </div>
  );
}

/** The signed-in line at a glance: plan, usage against its cap, device month, upgrade. */
export default function PlanPanel({ account: loaded }: { account: { account: AccountContext | null } | null }) {
  const t = useT();
  const { ask } = useStoreFrame();
  if (!loaded) return <Skeleton className="h-[188px]" />;
  const account = loaded.account;
  if (!account) {
    return (
      <Panel title={t("Your plan")} action={<AskButton label={t("Ask for a plan")} onClick={() => ask(t("Which plan would suit a new line?"))} />}>
        <p className="px-[18px] pb-3.5 text-[13.5px] leading-snug text-(--ink-soft)">{t(NO_LINE)}</p>
      </Panel>
    );
  }
  const plan = account.current_plan;
  const usage = usageOf(account);
  const upgrade = account.upgrade_eligibility;
  return (
    <Panel title={t("Your plan")} action={<AskButton label={t("Ask if a plan fits")} onClick={() => ask(t(ASK_PLAN_FIT))} />}>
      <div className="px-[18px] pb-3">
        <Row label={t("Plan")}>
          <span className="font-semibold">{plan.name}</span>
          {plan.price_per_month != null ? <span className="am-mono text-(--ink-soft)"> · {formatPrice(plan.price_per_month)}/mo</span> : null}
        </Row>
        <Row label={t("Data")}>
          <div className="flex items-center gap-2.5">
            <span className={`am-mono text-[12.5px] ${usage.over ? "font-semibold text-(--warn)" : "text-(--ink)"}`}>
              {usage.cap != null ? t("avg {avg} GB of {cap} GB", { avg: usage.avg, cap: usage.cap }) : t("avg {avg} GB", { avg: usage.avg })}
            </span>
            <MiniBar value={usage.share} tone={usage.over ? "warn" : "accent"} className="w-20" />
          </div>
        </Row>
        <Row label={t("Device")}>
          <span>{account.device.name}</span>
          <span className="am-mono text-(--ink-soft)">
            {" "}
            · {t("month {month}/{total}", { month: account.contract.month, total: account.contract.of_months })}
          </span>
        </Row>
        <Row label={t("Upgrade")}>
          {upgrade.eligible ? <Pill tone="accent" dot>{t("Upgrade open")}</Pill> : <Pill>{t("Upgrade later")}</Pill>}
        </Row>
      </div>
    </Panel>
  );
}
