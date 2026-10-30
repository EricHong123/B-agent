// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { ArrivingPanel, AskButton, Fact, Facts, formatDate, KindIcon, MiniBar, Notice, type Order, ORDER_NOUNS, PageHeader, Panel, Pill, Skeleton, StorePage, useStoreFrame, useT } from "web-shared";
import { formatPrice, usageOf } from "@/lib/format";
import type { AccountContext } from "@/lib/types";
import { ASK_PLAN_FIT, NO_LINE } from "../PlanPanel";


/** Dates inside account prose ("outright upgrade on 2026-09-20") in the page's date style. */
function withDates(text: string): string {
  return text.replace(/\d{4}-\d{2}-\d{2}/g, (day) => formatDate(day));
}

/** The last three billing cycles against the plan's cap, oldest first. */
function Cycles({ line }: { line: AccountContext }) {
  const t = useT();
  const cycles = line.recent_usage.cycles_gb_last_3 ?? [];
  const { cap } = usageOf(line);
  if (!cycles.length) return null;
  const scale = Math.max(cap ?? 0, ...cycles);
  return (
    <div className="mt-3.5 border-t border-(--line) px-[18px] pt-3">
      <p className="am-meta mb-2">{cap != null ? t("Last {n} cycles · {cap} GB allowance", { n: cycles.length, cap }) : t("Last {n} cycles", { n: cycles.length })}</p>
      <ul className="flex flex-col gap-1.5">
        {cycles.map((gb, index) => (
          <li key={index} className="flex items-center gap-3">
            <MiniBar value={gb / scale} tone={cap != null && gb > cap ? "warn" : "accent"} className="w-40" />
            <span className={`am-mono text-[12.5px] ${cap != null && gb > cap ? "font-semibold text-(--warn)" : "text-(--ink)"}`}>{gb} GB</span>
          </li>
        ))}
      </ul>
      {line.recent_usage.top_ups_last_3_months ? (
        <p className="am-mono mt-2 text-[12px] text-(--warn)">
          {line.recent_usage.top_up_spend_usd_last_3_months
            ? t("{n} top-ups ≈ {amount} in 3 months", { n: line.recent_usage.top_ups_last_3_months, amount: formatPrice(line.recent_usage.top_up_spend_usd_last_3_months) })
            : t("{n} top-ups in 3 months", { n: line.recent_usage.top_ups_last_3_months })}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The account as ACME Mobile has it: plan and usage, device and contract, orders. `account` is
 * null until the read lands; its inner `account` is null for a prospect.
 */
export default function AccountView({
  shopperName,
  account,
  failed,
  orders,
}: {
  shopperName: string;
  account: { account: AccountContext | null } | null;
  failed: boolean;
  orders: Order[] | null;
}) {
  const t = useT();
  const { ask } = useStoreFrame();
  const nouns = { ...ORDER_NOUNS, cardTitle: t("Orders") };
  const line = account?.account ?? null;
  return (
    <StorePage>
      <PageHeader title={t("Account")} subtitle={line ? t("{name}'s line, as ACME Mobile has it. Ask which plan fits this usage, or what an upgrade would cost.", { name: shopperName }) : undefined} />
      {!account ? (
        failed ? <Notice>{t("Couldn't load the account.")}</Notice> : <Skeleton className="h-[320px]" />
      ) : line ? (
        <>
          <Panel title={t("Plan and usage")} icon={<KindIcon icon="signal" tone="accent" size={30} />} action={<AskButton label={t("Ask if a plan fits")} onClick={() => ask(t(ASK_PLAN_FIT))} />} bodyClassName="pb-4">
            <div className="px-[18px]">
              <Facts>
                <Fact label={t("Plan")} value={line.current_plan.name} />
                <Fact label={t("Plan price")} value={line.current_plan.price_per_month != null ? t("{price}/mo", { price: formatPrice(line.current_plan.price_per_month) }) : "—"} />
                <Fact label={t("Monthly bill")} value={t("{price}/mo", { price: formatPrice(line.monthly_bill_usd) })} />
                <Fact label={t("Avg data")} value={`${usageOf(line).avg} GB`} tone={usageOf(line).over ? "warn" : undefined} />
              </Facts>
            </div>
            <Cycles line={line} />
          </Panel>
          <Panel
            title={t("Device and contract")}
            icon={<KindIcon icon="tag" tone="muted" size={30} />}
            action={<AskButton label={t("Ask about an upgrade")} onClick={() => ask(t("Am I due for a phone upgrade, and what would it cost?"))} />}
            bodyClassName="px-[18px] pb-4"
          >
            <Facts>
              <Fact label={t("Device")} value={line.device.name} />
              <Fact label={t("Contract")} value={t("Month {month} of {total}", { month: line.contract.month, total: line.contract.of_months })} />
              <Fact
                label={t("Installments left")}
                value={line.device.installment_usd ? `${line.device.installments_remaining} × ${formatPrice(line.device.installment_usd)}` : String(line.device.installments_remaining)}
              />
              <Fact label={t("Contract ends")} value={formatDate(line.contract.ends)} />
            </Facts>
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-(--ink-2)">
              {line.upgrade_eligibility.eligible ? <Pill tone="accent" dot>{t("Upgrade open")}</Pill> : <Pill>{t("Upgrade later")}</Pill>}
              <span>{withDates(line.upgrade_eligibility.reason)}</span>
            </div>
            {line.trade_in_estimate ? (
              <p className="am-mono mt-2 text-[12px] text-(--ink-soft)">
                {t("Trade-in about {amount} ({condition}). Quote good to {date}.", {
                  amount: formatPrice(line.trade_in_estimate.estimated_credit_usd),
                  condition: line.trade_in_estimate.condition_assumption,
                  date: formatDate(line.trade_in_estimate.quote_valid_through),
                })}
              </p>
            ) : null}
          </Panel>
        </>
      ) : (
        <Notice>{t(NO_LINE)}</Notice>
      )}
      {orders?.length ? <ArrivingPanel orders={orders} nouns={nouns} thumb={() => <KindIcon icon="box" size={40} />} /> : null}
    </StorePage>
  );
}
