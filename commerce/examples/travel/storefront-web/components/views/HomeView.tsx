// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useState } from "react";
import { ArrivingPanel, estimateOf, Greeting, HomeSection, type Order, type Starter, Starters, upcoming, useStoreFrame, useT } from "web-shared";
import { tripCount } from "@/lib/format";
import { TripThumb, useNouns } from "@/lib/orders";
import { PostcardWindow } from "../PostcardWindow";

const STARTERS: Starter[] = [
  { icon: "calendar", prompt: "Plan a long weekend in Lisbon" },
  { icon: "plane", prompt: "Compare flights to Kyoto" },
  { icon: "return", prompt: "Something refundable in Reykjavik" },
  { icon: "pin", prompt: "What's my Marrakesh booking status?" },
];

/** The keys of DESTINATION_GRADIENTS in lib/format.ts. */
const POSTCARD_CITIES = ["Lisbon", "Kyoto", "Mexico City", "Reykjavik", "Marrakesh", "Queenstown"];

/** Sends just before the 300ms mail animation ends. */
const MAILING_MS = 260;

const OPENER = "Say where you're headed and ACME Assistant finds the stays, flights, and days worth keeping.";

function Brief({ trips }: { trips: Order[] | null }) {
  const t = useT();
  const open = trips ? upcoming(trips) : [];
  if (!open.length) return <>{t(OPENER)}</>;
  const next = estimateOf(open[0])?.date;
  const count = tripCount(t, open.length);
  const opener = t(OPENER);
  return <>{next ? t("{count} coming up; the next starts {date}. {opener}", { count, date: next, opener }) : t("{count} coming up. {opener}", { count, opener })}</>;
}

function Postcards() {
  const t = useT();
  const { ask, chat } = useStoreFrame();
  const [mailingCity, setMailingCity] = useState<string | null>(null);
  const disabled = !chat || chat.busy || !chat.ready;
  const planTrip = (city: string) => {
    const request = () => ask(t("Plan a trip to {city}", { city }));
    // Reduced motion, or a card already on its way, sends at once.
    if (mailingCity || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      request();
      return;
    }
    setMailingCity(city);
    window.setTimeout(() => {
      setMailingCity(null);
      request();
    }, MAILING_MS);
  };
  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      {POSTCARD_CITIES.map((city, index) => (
        <button
          key={city}
          type="button"
          onClick={() => planTrip(city)}
          disabled={disabled}
          aria-label={t("Plan a trip to {city}", { city })}
          className="al-reveal-item"
          style={{ animationDelay: `${(index + 4) * 60}ms` }}
        >
          {/* Transforms live here; the button's reveal animation would pin them. */}
          <div
            className={`overflow-hidden rounded-(--radius) border border-(--line) ${
              index % 2 ? "al-postcard-rest al-postcard-rest--alt" : "al-postcard-rest"
            } ${mailingCity === city ? "al-postcard-mailing" : ""}`}
          >
            <PostcardWindow city={city} title={city} className="aspect-[4/3] w-full" />
          </div>
        </button>
      ))}
    </div>
  );
}

export default function HomeView({ travelerName, trips, tripsFailed, onSeeTrips }: { travelerName: string; trips: Order[] | null; tripsFailed: boolean; onSeeTrips: () => void }) {
  const t = useT();
  const nouns = useNouns();
  // The name sits in an <em>, so the sentence is split around a marker.
  const [before, after] = t("Where to, {name}?", { name: "\u0001" }).split("\u0001");
  return (
    <div className="flex flex-col gap-4">
      <Greeting
        title={
          <h1 className="al-hero">
            {before}
            <em>{travelerName}</em>
            {after}
          </h1>
        }
      >
        <Brief trips={trips} />
      </Greeting>
      <Starters items={STARTERS.map((starter) => ({ ...starter, prompt: t(starter.prompt) }))} />
      <ArrivingPanel orders={trips} failed={tripsFailed} nouns={nouns} thumb={(order) => <TripThumb order={order} />} onSeeAll={onSeeTrips} />
      <HomeSection title={t("Start from a postcard")} subtitle={t("Pick one and ACME Assistant starts planning")}>
        <Postcards />
      </HomeSection>
    </div>
  );
}
