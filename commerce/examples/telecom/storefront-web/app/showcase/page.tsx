// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders every card from lib/showcase-fixtures.ts; no API needed. */

import { useT } from "web-shared";
import OrderPanel from "@/components/OrderPanel";
import GenerativeBlock from "@/components/generative";
import { SHOWCASE } from "@/lib/showcase-fixtures";

const { account: ACCOUNT, ...FIXTURES } = SHOWCASE;

const SECTIONS = Object.keys(FIXTURES) as (keyof typeof FIXTURES)[];

/** Fixtures that render a card a second time name it here. */
const COMPONENT: Partial<Record<keyof typeof FIXTURES, string>> = {
  plan_matrix_memory: "plan_matrix",
  disclosure_plan: "disclosure",
};

const WITH_ACCOUNT = new Set<keyof typeof FIXTURES>(["products", "checkout"]);

function Section({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="am-meta mb-3 !text-[12px]">{name}</h2>
      <div data-component={name}>{children}</div>
    </section>
  );
}

export default function ShowcasePage() {
  const t = useT();
  return (
    <main className="relative z-[2] mx-auto max-w-3xl px-6 py-14">
      <p className="am-fig">
        <b>●</b> {t("ACME Mobile component showcase (fixture data)")}
      </p>
      {SECTIONS.map((name) => (
        <Section key={name} name={name}>
          <GenerativeBlock
            block={{ component: COMPONENT[name] ?? name, payload: FIXTURES[name] }}
            status="final"
            account={WITH_ACCOUNT.has(name) ? ACCOUNT : undefined}
          />
        </Section>
      ))}
      <Section name="order">
        <div className="flex h-[440px] flex-col overflow-hidden rounded-xl border border-(--line) bg-(--card)">
          <OrderPanel cart={null} account={null} />
        </div>
      </Section>
    </main>
  );
}
