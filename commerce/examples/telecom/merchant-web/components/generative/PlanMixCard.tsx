// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { formatMoney, formatNumber, formatRate, GenCard, GenCardHeader, KindIcon, Sparkline, useT } from "web-shared";
import type { PlanMixPayload, PlanMixRow } from "@/lib/types";

/** Renders present_plan_mix; every field is optional. */

function Stat({ label, value }: { label: string; value: string | null }) {
  if (value == null) return null;
  return (
    <span className="whitespace-nowrap">
      <span className="text-(--ink-soft)">{label} </span>
      <span className="am-mono font-semibold text-(--ink)">{value}</span>
    </span>
  );
}

function PlanRow({ plan }: { plan: PlanMixRow }) {
  const t = useT();
  const points = (plan.weeks ?? []).map((week) => week.subscribers).filter((value): value is number => value != null);
  const label = plan.title ?? plan.plan_id ?? t("Plan");
  return (
    <li className="px-3.5 py-2.5">
      <div className="flex items-center gap-3">
        <KindIcon icon={plan.kind === "home-internet" ? "home" : "signal"} tone="muted" size={30} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-(--ink)">{label}</div>
          <div className="am-mono text-[11.5px] text-(--ink-soft)">{[plan.plan_id, plan.price != null ? t("{price}/mo", { price: formatMoney(plan.price) }) : null].filter(Boolean).join(" · ")}</div>
        </div>
        {plan.subscribers != null ? (
          <div className="shrink-0 text-right">
            <div className="am-mono text-[15px] font-semibold leading-none text-(--ink)">{formatNumber(plan.subscribers)}</div>
            <div className="mt-0.5 text-[11px] text-(--ink-soft)">{t("lines")}
              {plan.share_pct != null ? ` · ${formatRate(plan.share_pct)}` : ""}</div>
          </div>
        ) : null}
      </div>
      {plan.share_pct != null ? (
        <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-(--well)">
          <div className="h-full rounded-full bg-(--ink)/70" style={{ width: `${Math.max(0, Math.min(100, plan.share_pct))}%` }} />
        </div>
      ) : null}
      <div className="mt-2 flex items-end justify-between gap-3">
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px]">
          <Stat label={t("Churn")} value={plan.churn_rate_pct != null ? formatRate(plan.churn_rate_pct) : null} />
          <Stat label="ARPU" value={plan.arpu != null ? formatMoney(plan.arpu) : null} />
          <Stat label={t("Margin / line")} value={plan.margin_per_line_usd != null ? formatMoney(plan.margin_per_line_usd) : null} />
          <Stat label={t("Avg usage")} value={plan.avg_usage_gb != null ? `${plan.avg_usage_gb.toFixed(1)} GB` : null} />
        </div>
        {points.length > 1 ? <Sparkline points={points} height={28} label={t("{label}, weekly subscribers", { label })} className="w-28 shrink-0" /> : null}
      </div>
      {plan.note ? <p className="mt-1.5 text-[12px] leading-snug text-(--ink-soft)">{plan.note}</p> : null}
    </li>
  );
}

export default function PlanMixCard({ payload }: { payload: PlanMixPayload }) {
  const t = useT();
  const plans = payload.plans ?? [];
  return (
    <GenCard>
      <GenCardHeader title={payload.title ?? t("Plan mix")} aside={payload.total_subscribers != null ? t("{n} lines on base", { n: formatNumber(payload.total_subscribers) }) : null} />
      {plans.length ? (
        <ul className="mt-2 divide-y divide-(--line) border-t border-(--line)">
          {plans.map((plan, index) => (
            <PlanRow key={plan.plan_id ?? index} plan={plan} />
          ))}
        </ul>
      ) : (
        <p className="px-3.5 pb-3.5 pt-2 text-[13px] text-(--ink-soft)">{t("No plan rows were returned for this base.")}</p>
      )}
      {payload.grain === "week" && plans.some((plan) => (plan.weeks ?? []).length >= 2) ? (
        <p className="border-t border-(--line) px-3.5 py-2 text-[11.5px] text-(--ink-soft)">{t("Trend lines are weekly subscriber counts over the reporting window.")}</p>
      ) : null}
    </GenCard>
  );
}
