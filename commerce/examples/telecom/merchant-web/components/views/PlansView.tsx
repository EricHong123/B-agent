// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useMemo, useState } from "react";
import {
  AskButton,
  Button,
  Fact,
  Facts,
  formatDate,
  formatDayMonth,
  formatMoney,
  formatNumber,
  formatRate,
  hasOptions,
  KindIcon,
  Notice,
  optionSummary,
  optionValuesLabel,
  PageHeader,
  Panel,
  Pill,
  PriceBand,
  priceLabel,
  QuotedAsData,
  SearchField,
  SectionTitle,
  Segmented,
  Sheet,
  Skeleton,
  titleCase,
  useResource,
  useT,
} from "web-shared";
import { fetchBase, fetchListingDetail, fetchListings } from "@/lib/api";
import { CATEGORY_LABELS, CATEGORY_NOUNS, CATEGORY_ORDER, LINE_CATEGORIES, LISTING_STATUS } from "@/lib/kinds";
import type { Listing, PlanMixRow } from "@/lib/types";

type Filter = "all" | "plans" | "home-internet" | "devices" | "add-ons";

const CATEGORY_ICONS = { plans: "signal", "home-internet": "home", devices: "box", "add-ons": "tag" } as const;

function StatusPill({ status }: { status: Listing["status"] }) {
  const t = useT();
  const style = LISTING_STATUS[status];
  return (
    <Pill tone={style.tone} dot>
      {t(style.label)}
    </Pill>
  );
}

function ContentCell({ quality }: { quality: Listing["content_quality"] }) {
  const t = useT();
  if (quality === "poor") return <Pill tone="danger">{t("Poor content")}</Pill>;
  if (quality === "needs_work") return <Pill tone="warn">{t("Needs work")}</Pill>;
  return <span className="text-[12.5px] text-(--ink-soft)">{t("Good")}</span>;
}

function CategoryIcon({ category }: { category: string }) {
  const icon = CATEGORY_ICONS[category as keyof typeof CATEGORY_ICONS] ?? "tag";
  return <KindIcon icon={icon} tone="muted" size={36} />;
}

function Rows({ rows }: { rows: [string, string | null][] }) {
  const shown = rows.filter(([, value]) => value != null && value !== "");
  if (!shown.length) return null;
  return (
    <div className="divide-y divide-(--line) rounded-[12px] border border-(--line)">
      {shown.map(([label, value]) => (
        <div key={label} className="flex items-baseline justify-between gap-3 px-3 py-1.5 text-[13px]">
          <span className="text-(--ink-soft)">{label}</span>
          <span className="am-mono text-right text-(--ink)">{value}</span>
        </div>
      ))}
    </div>
  );
}

function ProductSheet({ listingId, category, onClose, onAskAssistant }: { listingId: string; category: string; onClose: () => void; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const { data: detail, failed } = useResource(() => fetchListingDetail(listingId), [listingId]);
  const listing = detail?.listing;
  const pricing = detail?.pricing;
  const isLine = LINE_CATEGORIES.has(listing?.category ?? category) || pricing?.active_subscribers != null;
  const noun = t(CATEGORY_NOUNS[listing?.category ?? category] ?? "product");
  const ref = listing ? `${listing.title} (${listing.listing_id})` : listingId;
  const ask = (text: string) => {
    onClose();
    onAskAssistant(text);
  };

  return (
    <Sheet
      title={t(CATEGORY_LABELS[listing?.category ?? category] ?? titleCase(category))}
      detail={listingId}
      onClose={onClose}
      closeLabel={t("Close {noun} detail", { noun })}
      footer={
        listing ? (
          <Button
            variant="primary"
            icon="spark"
            className="flex-1"
            onClick={() =>
              ask(
                isLine
                  ? t("How is {ref} performing on subscribers, churn, and margin, and what would you change?", { ref })
                  : t("How is {ref} selling, and does the price or listing need work?", { ref }),
              )
            }
          >
            {t("Ask about this {noun}", { noun })}
          </Button>
        ) : null
      }
    >
      {failed && !listing ? (
        <p className="text-[13.5px] text-(--ink-soft)">{t("Couldn't load this {noun}.", { noun })}</p>
      ) : !listing ? (
        <>
          <Skeleton className="h-24" />
          <Skeleton className="h-40" />
        </>
      ) : (
        <>
          <div className="flex gap-3.5">
            <CategoryIcon category={listing.category ?? ""} />
            <div className="min-w-0">
              <h2 className="text-[17px] font-semibold leading-tight tracking-[-0.01em] text-(--ink)">{listing.title}</h2>
              {listing.short_description ? <p className="mt-1.5 text-[13px] leading-snug text-(--ink-soft)">{listing.short_description}</p> : null}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusPill status={listing.status} />
                {listing.content_quality && listing.content_quality !== "good" ? (
                  <Pill tone={listing.content_quality === "poor" ? "danger" : "warn"}>{listing.content_quality === "poor" ? t("Content is poor") : t("Content needs work")}</Pill>
                ) : null}
                {listing.category ? <Pill>{t(CATEGORY_LABELS[listing.category] ?? titleCase(listing.category))}</Pill> : null}
              </div>
            </div>
          </div>

          <Facts>
            <Fact label={isLine ? t("Price / mo") : hasOptions(listing) ? t("Price from") : t("Price")} value={formatMoney(listing.price)} />
            <Fact label={isLine ? t("Active lines") : t("Stock")} value={formatNumber(listing.stock)} />
            <Fact
              label={isLine ? t("ARPU") : t("Sold, 30 days")}
              value={isLine ? (pricing?.arpu != null ? formatMoney(pricing.arpu) : null) : listing.sales_last_30d != null ? formatNumber(listing.sales_last_30d) : null}
            />
            <Fact
              label={isLine ? t("Margin / line") : t("Margin")}
              value={isLine ? (pricing?.margin_per_line_usd != null ? formatMoney(pricing.margin_per_line_usd) : null) : pricing?.margin_pct != null ? formatRate(pricing.margin_pct) : null}
            />
          </Facts>

          {listing.variants?.length ? (
            <section>
              <SectionTitle aside={t("priced and stocked per variant")}>{t("Variants")}</SectionTitle>
              <ul className="divide-y divide-(--line) rounded-[10px] border border-(--line) text-[13px]">
                {listing.variants.map((variant) => (
                  <li key={variant.listing_id} className="flex items-center gap-3 px-3 py-1.5">
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left hover:underline"
                      onClick={() => ask(t("How is {title} in {options} ({id}) selling, and is the price right?", { title: variant.title, options: optionValuesLabel(variant), id: variant.listing_id }))}
                    >
                      <div className="font-medium text-(--ink)">{optionValuesLabel(variant)}</div>
                      <div className="text-[11.5px] tabular-nums text-(--ink-soft)">{variant.listing_id}</div>
                    </button>
                    <span className={`w-16 text-right tabular-nums ${variant.stock === 0 ? "font-semibold text-(--danger)" : "text-(--ink)"}`}>{formatNumber(variant.stock)}</span>
                    <span className="w-20 text-right tabular-nums text-(--ink)">{formatMoney(variant.price)}</span>
                    <StatusPill status={variant.status} />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {pricing && !listing.variants?.length ? (
            <section>
              <SectionTitle
                aside={[
                  pricing.unit_cost != null
                    ? t(isLine ? "wholesale {cost}" : "unit cost {cost}", {
                        cost: formatMoney(isLine && pricing.wholesale_cost_per_line_usd != null ? pricing.wholesale_cost_per_line_usd : pricing.unit_cost),
                      })
                    : "",
                  pricing.demand_signal ? t("demand {signal}", { signal: pricing.demand_signal }) : "",
                  pricing.last_changed ? t("changed {date}", { date: formatDate(pricing.last_changed) }) : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              >
                {t("Pricing")}
              </SectionTitle>
              {pricing.min_price != null && pricing.max_price != null ? <PriceBand current={pricing.current_price} floor={pricing.min_price} ceiling={pricing.max_price} /> : null}
              <div className="mt-3">
                <Rows
                  rows={[
                    [t("Share of base"), pricing.plan_mix_share_pct != null ? formatRate(pricing.plan_mix_share_pct) : null],
                    [t("Average usage"), pricing.avg_usage_gb != null ? `${pricing.avg_usage_gb.toFixed(1)} GB` : null],
                    [t("Margin"), isLine && pricing.margin_pct != null ? formatRate(pricing.margin_pct) : null],
                    [t("Return rate"), listing.return_rate_pct != null ? formatRate(listing.return_rate_pct) : null],
                  ]}
                />
              </div>
            </section>
          ) : null}

          {pricing?.active_promotions?.length ? (
            <section>
              <SectionTitle>{t("Active promotions")}</SectionTitle>
              <ul className="divide-y divide-(--line) rounded-[12px] bg-(--accent-soft)/60">
                {pricing.active_promotions.map((promo, index) => (
                  <li key={promo.change_id ?? index} className="px-3 py-2 text-[13px] leading-snug">
                    <div className="text-(--ink)">{promo.summary ?? t("Promotional window")}</div>
                    <div className="am-mono mt-0.5 text-[11.5px] text-(--ink-soft)">
                      {[
                        promo.promo_price != null ? t("{price}/mo", { price: formatMoney(promo.promo_price) }) : null,
                        promo.standing_price != null ? t("standing {price}", { price: formatMoney(promo.standing_price) }) : null,
                        promo.starts && promo.ends ? `${formatDayMonth(promo.starts)} – ${formatDayMonth(promo.ends)}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {listing.missing_attributes?.length ? (
            <section>
              <SectionTitle>{t("Missing from the listing")}</SectionTitle>
              <div className="flex flex-wrap items-center gap-1.5">
                {listing.missing_attributes.map((attribute) => (
                  <Pill key={attribute} tone="warn">
                    + {attribute}
                  </Pill>
                ))}
                <AskButton
                  label={t("Draft these attributes")}
                  onClick={() => ask(t("Draft the missing attributes ({attributes}) for {ref}.", { attributes: listing.missing_attributes?.join(", ") ?? "", ref }))}
                />
              </div>
            </section>
          ) : null}

          {listing.review_snippets?.length ? (
            <section>
              <SectionTitle aside={<QuotedAsData subject={t("Customer-written")} />}>{t("What customers say")}</SectionTitle>
              <div className="flex flex-col gap-1.5">
                {listing.review_snippets.map((snippet, index) => (
                  <blockquote key={index} className="rounded-[10px] bg-(--ground) px-3 py-2 text-[13px] leading-snug text-(--ink-2)">
                    &ldquo;{snippet}&rdquo;
                  </blockquote>
                ))}
              </div>
            </section>
          ) : null}

          {listing.long_description ? (
            <section>
              <SectionTitle>{t("Description")}</SectionTitle>
              <p className="whitespace-pre-line text-[13px] leading-relaxed text-(--ink-2)">{listing.long_description}</p>
            </section>
          ) : null}
        </>
      )}
    </Sheet>
  );
}

function ProductTable({
  category,
  listings,
  baseRows,
  onOpen,
}: {
  category: string;
  listings: Listing[];
  baseRows: Map<string, PlanMixRow> | null;
  onOpen: (id: string) => void;
}) {
  const t = useT();
  const lineCategory = LINE_CATEGORIES.has(category);
  return (
    <div className="panel-scroll @container overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-left text-[12px] font-semibold text-(--ink-soft)">
            <th className="py-2.5 pl-[18px] pr-3 font-semibold">{t(titleCase(CATEGORY_NOUNS[category] ?? "product"))}</th>
            <th className="px-3 py-2.5 text-right font-semibold">{lineCategory ? t("Price / mo") : t("Price")}</th>
            <th className="px-3 py-2.5 text-right font-semibold">{lineCategory ? t("Active lines") : t("Stock")}</th>
            {lineCategory ? (
              <>
                <th className="px-3 py-2.5 text-right font-semibold">{t("Churn")}</th>
                <th className="hidden px-3 py-2.5 text-right font-semibold @2xl:table-cell">{t("ARPU")}</th>
                <th className="hidden px-3 py-2.5 text-right font-semibold @3xl:table-cell">{t("Margin / line")}</th>
              </>
            ) : (
              <th className="px-3 py-2.5 font-semibold">{t("Content")}</th>
            )}
            <th className="py-2.5 pl-3 pr-[18px] font-semibold">{t("Status")}</th>
          </tr>
        </thead>
        <tbody>
          {listings.map((listing) => {
            const base = baseRows?.get(listing.listing_id);
            return (
              <tr
                key={listing.listing_id}
                onClick={() => onOpen(listing.listing_id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onOpen(listing.listing_id);
                  }
                }}
                tabIndex={0}
                aria-label={t("Open {title}", { title: listing.title })}
                className="cursor-pointer border-t border-(--line) transition-colors hover:bg-(--ground)/70 focus-visible:bg-(--ground)/70 focus-visible:outline-none"
              >
                <td className="py-2 pl-[18px] pr-3">
                  <div className="flex items-center gap-3">
                    <CategoryIcon category={category} />
                    <div className="min-w-0">
                      <div className="text-[13.5px] font-medium leading-snug text-(--ink)">{listing.title}</div>
                      <div className="am-mono text-[11.5px] text-(--ink-soft)">
                        {listing.listing_id}
                        {hasOptions(listing) ? <span> · {optionSummary(listing)}</span> : null}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="am-mono px-3 py-2 text-right text-[13px] text-(--ink)">{lineCategory ? formatMoney(listing.price) : priceLabel(listing)}</td>
                <td className="am-mono px-3 py-2 text-right text-[13px] text-(--ink)">{formatNumber(listing.stock)}</td>
                {lineCategory ? (
                  <>
                    <td className="am-mono px-3 py-2 text-right text-[13px] text-(--ink)">{base?.churn_rate_pct != null ? formatRate(base.churn_rate_pct) : "—"}</td>
                    <td className="am-mono hidden px-3 py-2 text-right text-[13px] text-(--ink) @2xl:table-cell">{base?.arpu != null ? formatMoney(base.arpu) : "—"}</td>
                    <td className="am-mono hidden px-3 py-2 text-right text-[13px] text-(--ink) @3xl:table-cell">
                      {base?.margin_per_line_usd != null ? formatMoney(base.margin_per_line_usd) : "—"}
                    </td>
                  </>
                ) : (
                  <td className="px-3 py-2">
                    <ContentCell quality={listing.content_quality} />
                  </td>
                )}
                <td className="py-2 pl-3 pr-[18px]">
                  <StatusPill status={listing.status} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function groupListings(listings: Listing[]): { category: string; rows: Listing[] }[] {
  const groups = new Map<string, Listing[]>();
  for (const listing of listings) {
    const category = listing.category ?? "other";
    (groups.get(category) ?? groups.set(category, []).get(category)!).push(listing);
  }
  const rank = (category: string) => (CATEGORY_ORDER.indexOf(category) + 1 || CATEGORY_ORDER.length + 1);
  return [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b)).map(([category, rows]) => ({ category, rows }));
}

export default function PlansView({ refreshKey, onAskAssistant }: { refreshKey: number; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const { data: listingData, failed } = useResource(fetchListings, [refreshKey]);
  // Base rows keyed by plan_id; the tables render without them when /base is unavailable.
  const { data: base } = useResource(fetchBase, [refreshKey]);
  const baseRows = useMemo(
    () => (base ? new Map(base.plans.filter((row) => row.plan_id).map((row) => [row.plan_id as string, row])) : null),
    [base],
  );
  const listings = listingData?.listings ?? null;
  const total = listingData ? (listingData.total ?? listingData.listings.length) : null;
  const [openListing, setOpenListing] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const { groups, counts } = useMemo(() => {
    const all = listings ?? [];
    const needle = query.trim().toLowerCase();
    const visible = all.filter(
      (listing) =>
        (filter === "all" || listing.category === filter) &&
        (!needle ||
          listing.title.toLowerCase().includes(needle) ||
          listing.listing_id.toLowerCase().includes(needle) ||
          Object.values(listing.attributes ?? {}).some((value) => value.toLowerCase().includes(needle))),
    );
    const byCategory = (category: string) => all.filter((listing) => listing.category === category).length;
    return {
      groups: groupListings(visible),
      counts: { all: all.length, plans: byCategory("plans"), "home-internet": byCategory("home-internet"), devices: byCategory("devices"), "add-ons": byCategory("add-ons") },
    };
  }, [listings, query, filter]);

  const needsWork = (listings ?? []).filter((listing) => listing.content_quality && listing.content_quality !== "good").length;
  const summary = listings
    ? [
        total != null && total > listings.length ? t("{shown} of {total} products", { shown: formatNumber(listings.length), total: formatNumber(total) }) : null,
        t("{n} plans", { n: counts.plans + counts["home-internet"] }),
        t("{n} devices", { n: counts.devices }),
        t("{n} add-ons", { n: counts["add-ons"] }),
        needsWork ? t("{n} need content work", { n: needsWork }) : "",
      ]
        .filter(Boolean)
        .join(" · ")
    : undefined;
  const openCategory = openListing ? (listings?.find((listing) => listing.listing_id === openListing)?.category ?? "") : "";

  return (
    <div className="ac-reveal flex flex-col gap-4">
      <PageHeader title={t("Catalog")} subtitle={summary}>
        <Button variant="secondary" icon="spark" onClick={() => onAskAssistant(t("Which plans are carrying the thinnest margin per line, and what would you change?"))}>
          {t("Ask about the catalog")}
        </Button>
      </PageHeader>

      {failed && !listings ? (
        <Notice>{t("The telecom API isn't reachable, so the catalog can't load.")}</Notice>
      ) : !listings ? (
        <Skeleton className="h-96" />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2.5">
            <SearchField value={query} onChange={setQuery} placeholder={t("Search by name, ID, or attribute")} label={t("Search the catalog")} className="min-w-[260px] flex-1 sm:max-w-sm" />
            <Segmented<Filter>
              label={t("Filter the catalog")}
              value={filter}
              onChange={setFilter}
              options={[
                { id: "all", label: t("All"), count: counts.all },
                { id: "plans", label: t("Plans"), count: counts.plans },
                { id: "home-internet", label: t("Home internet"), count: counts["home-internet"] },
                { id: "devices", label: t("Devices"), count: counts.devices },
                { id: "add-ons", label: t("Add-ons"), count: counts["add-ons"] },
              ]}
            />
          </div>

          {groups.length === 0 ? <Notice>{t("Nothing in the catalog matches.")}</Notice> : null}

          {groups.map(({ category, rows }) => (
            <Panel key={category} title={t(CATEGORY_LABELS[category] ?? titleCase(category))} subtitle={String(rows.length)}>
              <ProductTable category={category} listings={rows} baseRows={baseRows} onOpen={setOpenListing} />
            </Panel>
          ))}
        </>
      )}

      {openListing ? <ProductSheet listingId={openListing} category={openCategory} onClose={() => setOpenListing(null)} onAskAssistant={onAskAssistant} /> : null}
    </div>
  );
}
