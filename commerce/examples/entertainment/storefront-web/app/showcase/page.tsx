// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Live-state cards read the default LiveContext, so no countdown runs. */

import type { ReactNode } from "react";
import GenerativeBlock from "@/components/generative";
import { ComponentBones } from "@/components/generative/Bones";
import { TonightStrip } from "@/components/NightPanel";
import WalletPass from "@/components/WalletPass";
import { OfferBannerInner } from "@/components/OfferBanner";
import {
  SHOWCASE,
  SHOWCASE_OFFER,
  SHOWCASE_TONIGHT,
  SHOWCASE_WALLET_ACTIVE,
  SHOWCASE_WALLET_PENDING,
} from "@/lib/showcase-fixtures";

const SECTIONS = Object.keys(SHOWCASE) as (keyof typeof SHOWCASE)[];

const RENDERS_AS: Partial<Record<keyof typeof SHOWCASE, string>> = {
  resale: "products",
  disclosure_resale: "disclosure",
};

function Section({
  name,
  narrow,
  children,
}: {
  name: string;
  narrow?: boolean;
  children: ReactNode;
}) {
  return (
    <section className="mt-10">
      <h2 className="at-eyebrow mb-3">{name}</h2>
      <div data-component={name} className={narrow ? "max-w-[390px]" : undefined}>
        {children}
      </div>
    </section>
  );
}

export default function ShowcasePage() {
  const offer = {
    ...SHOWCASE_OFFER,
    deadline: Date.now() + SHOWCASE_OFFER.seconds_remaining * 1000,
  };
  return (
    <main className="relative z-[2] mx-auto max-w-2xl px-6 py-14">
      <p className="at-stub-caption">
        <b>●</b> ACME Tickets component showcase (fixture data)
      </p>
      {SECTIONS.map((name) => (
        <Section key={name} name={name}>
          <GenerativeBlock
            block={{ component: RENDERS_AS[name] ?? name, payload: SHOWCASE[name] }}
            status="final"
          />
        </Section>
      ))}
      <Section name="tonight-strip" narrow>
        <TonightStrip
          product={SHOWCASE_TONIGHT.product}
          quantity={SHOWCASE_TONIGHT.quantity}
          total={SHOWCASE_TONIGHT.total}
          deadline={Date.now() + SHOWCASE_TONIGHT.seconds_remaining * 1000}
        />
      </Section>
      <Section name="wallet-pass" narrow>
        <WalletPass ticket={SHOWCASE_WALLET_ACTIVE} />
      </Section>
      <Section name="wallet-pass-pending" narrow>
        <WalletPass ticket={SHOWCASE_WALLET_PENDING} />
      </Section>
      <Section name="pending-skeleton">
        <ComponentBones component="venue_map" />
      </Section>
      <Section name="offer-banner">
        <OfferBannerInner offer={offer} product={SHOWCASE_OFFER.product} onClaim={() => {}} />
      </Section>
    </main>
  );
}
