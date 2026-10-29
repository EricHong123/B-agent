// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Shown from a presentation tool call until its `ui` event lands. */

import { useT } from "web-shared";

export const PRESENTATION_COMPONENTS: Record<string, string> = {
  present_products: "products",
  present_comparison: "comparison",
  present_plan: "plan",
  present_guide: "guide",
  present_order_status: "order_status",
  checkout: "checkout",
  present_disclosure: "disclosure",
  present_venue_map: "venue_map",
  present_hold: "hold",
};

function VenueMapBones() {
  return (
    <div className="grid gap-4 sm:grid-cols-[1.5fr_1fr]">
      <div className="flex flex-col items-center gap-2 rounded-(--radius) border border-(--line) bg-(--ground) p-4">
        <div className="at-skeleton h-5 w-2/5" />
        <div className="at-skeleton h-6 w-3/5" />
        <div className="at-skeleton h-7 w-11/12" />
        <div className="at-skeleton h-9 w-4/5" />
      </div>
      <div className="flex flex-col gap-1.5">
        {[0, 1, 2].map((row) => (
          <div
            key={row}
            className="flex items-center gap-2.5 rounded-(--radius) border border-(--line) px-2.5 py-2"
          >
            <div className="at-skeleton h-3 w-3 shrink-0" />
            <div className="at-skeleton h-3.5 flex-1" />
            <div className="at-skeleton h-3.5 w-12 shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}

function CardBones() {
  return (
    <div className="flex gap-3 rounded-(--radius) border border-(--line) p-3">
      <div className="at-skeleton h-[64px] w-[52px] shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-2 py-1">
        <div className="at-skeleton h-4 w-3/5" />
        <div className="at-skeleton h-3 w-2/5" />
        <div className="at-skeleton h-3 w-1/3" />
      </div>
    </div>
  );
}

function ColumnsBones() {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {[0, 1].map((column) => (
        <div
          key={column}
          className="flex flex-col gap-2 rounded-(--radius) border border-(--line) p-4"
        >
          <div className="at-skeleton h-5 w-4/5" />
          <div className="at-skeleton h-7 w-3/5" />
          <div className="at-skeleton h-3 w-full" />
          <div className="at-skeleton h-3 w-2/3" />
        </div>
      ))}
    </div>
  );
}

function TapeBones() {
  return (
    <div className="mx-auto flex w-full max-w-[360px] flex-col gap-2.5 border-x border-(--line) bg-(--well)/60 p-4">
      <div className="at-skeleton mx-auto h-4 w-4/5" />
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex items-center gap-2">
          <div className="at-skeleton h-3 w-2/5" />
          <div className="flex-1" />
          <div className="at-skeleton h-3 w-14" />
        </div>
      ))}
      <div className="at-skeleton mx-auto mt-1 h-8 w-2/5" />
    </div>
  );
}

export function TextBones() {
  return (
    <div className="flex flex-col gap-2">
      <div className="at-skeleton h-4 w-3/5" />
      <div className="at-skeleton h-4 w-2/5" />
    </div>
  );
}

export function ComponentBones({ component }: { component: string }) {
  const t = useT();
  return (
    <div className="at-card overflow-hidden p-4 sm:p-5" aria-label={t("ACME Assistant is working")}>
      <Bones component={component} />
    </div>
  );
}

function Bones({ component }: { component: string }) {
  switch (component) {
    case "venue_map":
      return <VenueMapBones />;
    case "products":
      return <CardBones />;
    case "comparison":
      return <ColumnsBones />;
    case "disclosure":
      return <TapeBones />;
    case "checkout":
    case "hold":
      return (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="at-skeleton h-5 w-32" />
            <div className="at-skeleton h-9 w-24" />
          </div>
          <CardBones />
        </div>
      );
    default:
      return <TextBones />;
  }
}
