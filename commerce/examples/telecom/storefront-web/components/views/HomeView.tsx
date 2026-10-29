// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { Greeting, type Starter, Starters, useT } from "web-shared";
import { formatPrice, usageOf } from "@/lib/format";
import type { AccountContext } from "@/lib/types";
import PlanPanel, { ASK_PLAN_FIT, NO_LINE } from "../PlanPanel";

const STARTERS: Starter[] = [
  { icon: "signal", prompt: ASK_PLAN_FIT },
  { icon: "tag", prompt: "Am I due for a phone upgrade?" },
  { icon: "home", prompt: "Would bundling home internet save me money?" },
  { icon: "search", prompt: "What's the early termination fee?" },
];

/** One sentence on where the line stands: over its allowance and what that costs, or on track. */
function Brief({ account }: { account: AccountContext }) {
  const t = useT();
  const usage = usageOf(account);
  const topUps = account.recent_usage.top_up_spend_usd_last_3_months;
  if (usage.over) {
    return (
      <>
        <span className="font-semibold text-(--warn)">
          {topUps
            ? t("You average {avg} GB on a {cap} GB plan; top-ups came to {amount} over three months.", { avg: usage.avg, cap: usage.cap ?? "", amount: formatPrice(topUps) })
            : t("You average {avg} GB on a {cap} GB plan.", { avg: usage.avg, cap: usage.cap ?? "" })}
        </span>{" "}
        {t("Ask which plan fits, and ACME Assistant compares them against your usage with the terms as written.")}
      </>
    );
  }
  return <>{t("Your line is on track this cycle. Ask about plans, phones, or home fiber, and ACME Assistant quotes the terms as written.")}</>;
}

export default function HomeView({ shopperName, account }: { shopperName: string; account: { account: AccountContext | null } | null }) {
  const t = useT();
  const line = account?.account ?? null;
  const starters = STARTERS.map((starter) => ({ ...starter, prompt: t(starter.prompt) }));
  // The title's emphasis is marked <b>…</b> in the string so each language places it where its grammar does.
  const title = t("Let's read the <b>fine print</b> together, {name}.", { name: shopperName }).split(/<b>(.*?)<\/b>/);
  return (
    <div className="flex flex-col gap-4">
      <Greeting
        eyebrow={
          account ? (
            <span className="am-fig">
              <b>●</b> {line ? t("{plan} · line active", { plan: line.current_plan.name }) : t("No line yet")}
            </span>
          ) : null
        }
        title={
          <h1 className="am-hero">
            {title.map((part, index) => (index % 2 ? <strong key={index}>{part}</strong> : part))}
          </h1>
        }
      >
        {account ? line ? <Brief account={line} /> : t(NO_LINE) : null}
      </Greeting>
      <Starters items={starters} />
      <PlanPanel account={account} />
    </div>
  );
}
