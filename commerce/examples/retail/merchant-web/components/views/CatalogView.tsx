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
  formatMoney,
  formatNumber,
  formatRate,
  hasOptions,
  Notice,
  optionSummary,
  optionValuesLabel,
  PageHeader,
  Panel,
  Pill,
  PriceBand,
  QuotedAsData,
  SearchField,
  SectionTitle,
  Segmented,
  Sheet,
  Skeleton,
  Thumb,
  titleCase,
  type Translate,
  useResource,
  useT,
} from "web-shared";
import { api, fetchAlerts, fetchListingDetail, fetchListings } from "@/lib/api";
import { formatCategoryLabel } from "@/lib/format";
import { INVENTORY_KINDS, LISTING_STATUS } from "@/lib/kinds";
import { coverText } from "@/lib/labels";
import type { InventoryAlert, Listing } from "@/lib/types";

type Filter = "all" | "active" | "low_stock" | "content" | "inactive";

/** "From $349" on a family record, whose price is its lowest variant's; the plain price otherwise. */
function priceText(listing: Listing, t: Translate): string {
  const money = formatMoney(listing.price, listing.currency);
  return hasOptions(listing) ? t("From {price}", { price: money }) : money;
}

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

/** Why a listing sorts into the attention group; lower ranks list first. */
function attentionRank(listing: Listing, alert: InventoryAlert | undefined): number | null {
  if (listing.status === "out_of_stock" || listing.stock === 0) return 0;
  if (alert?.kind === "low_stock") return 1;
  if (listing.content_quality && listing.content_quality !== "good") return 2;
  if (listing.status === "paused" || listing.status === "draft") return 3;
  if (alert?.kind === "slow_mover") return 4;
  return null;
}

function StockCell({ listing, alert }: { listing: Listing; alert?: InventoryAlert }) {
  const t = useT();
  const soldOut = listing.stock === 0;
  const low = alert?.kind === "low_stock" && !soldOut;
  return (
    <div className={`text-right tabular-nums ${soldOut ? "text-(--danger)" : low ? "text-(--warn)" : "text-(--ink)"}`}>
      <div className={soldOut || low ? "font-semibold" : ""}>{formatNumber(listing.stock)}</div>
      {low && alert?.days_of_cover != null ? (
        <div className="whitespace-nowrap text-[11.5px] font-medium text-(--ink-soft)">{coverText(t, alert.days_of_cover)}</div>
      ) : soldOut && alert?.sales_last_30d ? (
        <div className="whitespace-nowrap text-[11.5px] font-medium text-(--ink-soft)">{t("{count} sold in 30 days", { count: formatNumber(alert.sales_last_30d) })}</div>
      ) : null}
    </div>
  );
}

function ListingSheet({
  listingId,
  alert,
  onClose,
  onAskAssistant,
}: {
  listingId: string;
  alert?: InventoryAlert;
  onClose: () => void;
  onAskAssistant: (text: string) => void;
}) {
  const t = useT();
  const { data: detail, failed } = useResource(() => fetchListingDetail(listingId), [listingId]);
  const listing = detail?.listing;
  const pricing = detail?.pricing;
  const ref = listing ? `${listing.title} (${listing.listing_id})` : listingId;
  const ask = (text: string) => {
    onClose();
    onAskAssistant(text);
  };

  return (
    <Sheet
      title={t("Listing")}
      detail={listingId}
      onClose={onClose}
      closeLabel={t("Close listing detail")}
      footer={
        listing ? (
          <>
            <Button variant="primary" icon="spark" className="flex-1" onClick={() => ask(t("Tell me how {ref} is doing and what you would change.", { ref }))}>
              {t("Ask about this listing")}
            </Button>
            {alert?.kind === "low_stock" ? (
              <Button variant="secondary" onClick={() => ask(t("Draft a restock plan for {ref}.", { ref }))}>
                {t("Draft restock")}
              </Button>
            ) : null}
          </>
        ) : null
      }
    >
      {failed ? (
        <p className="text-[13.5px] text-(--ink-soft)">{t("Couldn't load this listing.")}</p>
      ) : !listing ? (
        <>
          <Skeleton className="h-24" />
          <Skeleton className="h-40" />
        </>
      ) : (
        <>
          <div className="flex gap-3.5">
            <Thumb src={api.assetUrl(listing.image_url)} alt={listing.title} size={84} />
            <div className="min-w-0">
              <h2 className="text-[17px] font-semibold leading-tight tracking-[-0.01em] text-(--ink)">{listing.title}</h2>
              {listing.short_description ? <p className="mt-1.5 text-[13px] leading-snug text-(--ink-soft)">{listing.short_description}</p> : null}
              <div className="mt-2 flex flex-wrap gap-1.5">
                <StatusPill status={listing.status} />
                {listing.content_quality && listing.content_quality !== "good" ? (
                  <Pill tone={listing.content_quality === "poor" ? "danger" : "warn"}>{listing.content_quality === "poor" ? t("Content is poor") : t("Content needs work")}</Pill>
                ) : null}
                {listing.category ? <Pill>{formatCategoryLabel(listing.category, t)}</Pill> : null}
              </div>
            </div>
          </div>

          <Facts>
            <Fact label={hasOptions(listing) ? t("Price from") : t("Price")} value={formatMoney(listing.price, listing.currency)} />
            <Fact label={t("In stock")} value={formatNumber(listing.stock)} tone={listing.stock === 0 ? "danger" : alert?.kind === "low_stock" ? "warn" : undefined} />
            <Fact label={t("Sold, 30 days")} value={listing.sales_last_30d != null ? formatNumber(listing.sales_last_30d) : null} />
            <Fact
              label={pricing?.margin_pct != null ? t("Margin") : t("Return rate")}
              value={pricing?.margin_pct != null ? formatRate(pricing.margin_pct) : listing.return_rate_pct != null ? formatRate(listing.return_rate_pct) : null}
            />
          </Facts>

          {listing.variants?.length ? <VariantsTable variants={listing.variants} onAsk={ask} /> : null}

          {pricing && !hasOptions(listing) ? (
            <section>
              <SectionTitle
                aside={[
                  pricing.unit_cost != null ? t("unit cost {amount}", { amount: formatMoney(pricing.unit_cost) }) : "",
                  pricing.demand_signal ? t("demand {signal}", { signal: t(titleCase(pricing.demand_signal)).toLowerCase() }) : "",
                  pricing.last_changed ? t("changed {date}", { date: formatDate(pricing.last_changed) }) : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
              >
                {t("Pricing")}
              </SectionTitle>
              {pricing.min_price != null && pricing.max_price != null ? <PriceBand current={pricing.current_price} floor={pricing.min_price} ceiling={pricing.max_price} /> : null}
              {listing.return_rate_pct != null && pricing.margin_pct != null ? (
                <p className="mt-2 text-[12.5px] tabular-nums text-(--ink-soft)">{t("Return rate")} {formatRate(listing.return_rate_pct)}</p>
              ) : null}
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
              <SectionTitle aside={<QuotedAsData subject={t("Customer-written")} />}>{t("What buyers say")}</SectionTitle>
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

/** A family listing's variants: what price and stock are read and written against. */
function VariantsTable({ variants, onAsk }: { variants: Listing[]; onAsk: (text: string) => void }) {
  const t = useT();
  return (
    <section>
      <SectionTitle aside={t("{count} variants · priced and stocked per variant", { count: variants.length })}>{t("Variants")}</SectionTitle>
      <div className="overflow-x-auto rounded-[10px] border border-(--line)">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="bg-(--ground) text-left text-[11.5px] font-medium uppercase tracking-[0.04em] text-(--ink-soft)">
              <th className="px-3 py-1.5">{t("Variant")}</th>
              <th className="px-3 py-1.5 text-right">{t("Stock")}</th>
              <th className="px-3 py-1.5 text-right">{t("Price")}</th>
              <th className="px-3 py-1.5">{t("Status")}</th>
            </tr>
          </thead>
          <tbody>
            {variants.map((variant) => (
              <tr key={variant.listing_id} className="border-t border-(--line)">
                <td className="px-3 py-1.5">
                  <button
                    type="button"
                    className="text-left text-(--ink) hover:underline"
                    onClick={() => onAsk(t("How is {title} in {options} ({id}) priced, and would you change it?", { title: variant.title, options: optionValuesLabel(variant), id: variant.listing_id }))}
                  >
                    <div className="font-medium">{optionValuesLabel(variant)}</div>
                    <div className="text-[11.5px] tabular-nums text-(--ink-soft)">{variant.listing_id}</div>
                  </button>
                </td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${variant.stock === 0 ? "font-semibold text-(--danger)" : "text-(--ink)"}`}>{formatNumber(variant.stock)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums text-(--ink)">{formatMoney(variant.price)}</td>
                <td className="px-3 py-1.5">
                  <StatusPill status={variant.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ListingRow({ listing, alert, onOpen }: { listing: Listing; alert?: InventoryAlert; onOpen: () => void }) {
  const t = useT();
  return (
    <tr
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      tabIndex={0}
      aria-label={t("Open {title}", { title: listing.title })}
      className="cursor-pointer border-t border-(--line) transition-colors hover:bg-(--ground)/70 focus-visible:bg-(--ground)/70 focus-visible:outline-none"
    >
      <td className="py-2 pl-[18px] pr-3">
        <div className="flex items-center gap-3">
          <Thumb src={api.assetUrl(listing.image_url)} alt="" />
          <div className="min-w-0">
            <div className="text-[13.5px] font-medium leading-snug text-(--ink)">{listing.title}</div>
            <div className="text-[12px] tabular-nums text-(--ink-soft)">
              {listing.listing_id}
              {hasOptions(listing) ? <span> · {optionSummary(listing)}</span> : null}
              {alert?.kind === "slow_mover" ? <span> · {t(INVENTORY_KINDS.slow_mover.label).toLowerCase()}</span> : null}
            </div>
          </div>
        </div>
      </td>
      <td className="hidden px-3 py-2 text-[13px] text-(--ink-soft) @4xl:table-cell">{listing.category ? formatCategoryLabel(listing.category, t) : "—"}</td>
      <td className="px-3 py-2">
        <StockCell listing={listing} alert={alert} />
      </td>
      <td className="px-3 py-2 text-right text-[13.5px] tabular-nums text-(--ink)">{priceText(listing, t)}</td>
      <td className="px-3 py-2">
        <StatusPill status={listing.status} />
      </td>
      <td className="hidden py-2 pl-3 pr-[18px] @2xl:table-cell">
        <ContentCell quality={listing.content_quality} />
      </td>
    </tr>
  );
}

function ListingTable({ listings, alerts, onOpen }: { listings: Listing[]; alerts: Map<string, InventoryAlert>; onOpen: (id: string) => void }) {
  const t = useT();
  return (
    <div className="panel-scroll @container overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-left text-[12px] font-semibold text-(--ink-soft)">
            <th className="py-2.5 pl-[18px] pr-3 font-semibold">{t("Listing")}</th>
            <th className="hidden px-3 py-2.5 font-semibold @4xl:table-cell">{t("Category")}</th>
            <th className="px-3 py-2.5 text-right font-semibold">{t("Stock")}</th>
            <th className="px-3 py-2.5 text-right font-semibold">{t("Price")}</th>
            <th className="px-3 py-2.5 font-semibold">{t("Status")}</th>
            <th className="hidden py-2.5 pl-3 pr-[18px] font-semibold @2xl:table-cell">{t("Content")}</th>
          </tr>
        </thead>
        <tbody>
          {listings.map((listing) => (
            <ListingRow key={listing.listing_id} listing={listing} alert={alerts.get(listing.listing_id)} onOpen={() => onOpen(listing.listing_id)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CatalogView({ refreshKey, onAskAssistant }: { refreshKey: number; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const { data: listingData, failed } = useResource(fetchListings, [refreshKey]);
  // Inventory alerts annotate the rows with days of cover and the slow-mover mark.
  const { data: alertData } = useResource(fetchAlerts, [refreshKey]);
  const listings = listingData?.listings ?? null;
  const total = listingData ? (listingData.total ?? listingData.listings.length) : null;
  const alerts = useMemo(() => new Map((alertData?.inventory ?? []).map((alert) => [alert.listing_id, alert])), [alertData]);
  const [openListing, setOpenListing] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const { attention, rest, counts } = useMemo(() => {
    const all = listings ?? [];
    const needle = query.trim().toLowerCase();
    const matches = (listing: Listing) =>
      !needle ||
      listing.title.toLowerCase().includes(needle) ||
      listing.listing_id.toLowerCase().includes(needle) ||
      (listing.category ?? "").includes(needle) ||
      Object.values(listing.attributes ?? {}).some((value) => value.toLowerCase().includes(needle));
    const inFilter = (listing: Listing) => {
      const alert = alerts.get(listing.listing_id);
      if (filter === "active") return listing.status === "active";
      if (filter === "low_stock") return listing.stock === 0 || alert?.kind === "low_stock";
      if (filter === "content") return Boolean(listing.content_quality && listing.content_quality !== "good");
      if (filter === "inactive") return listing.status !== "active";
      return true;
    };
    const visible = all.filter((listing) => matches(listing) && inFilter(listing));
    const flagged = visible
      .map((listing) => ({ listing, rank: attentionRank(listing, alerts.get(listing.listing_id)) }))
      .filter((entry): entry is { listing: Listing; rank: number } => entry.rank != null)
      .sort((a, b) => a.rank - b.rank);
    const flaggedIds = new Set(flagged.map((entry) => entry.listing.listing_id));
    return {
      attention: flagged.map((entry) => entry.listing),
      rest: visible.filter((listing) => !flaggedIds.has(listing.listing_id)),
      counts: {
        all: all.length,
        active: all.filter((listing) => listing.status === "active").length,
        low_stock: all.filter((listing) => listing.stock === 0 || alerts.get(listing.listing_id)?.kind === "low_stock").length,
        content: all.filter((listing) => listing.content_quality && listing.content_quality !== "good").length,
        inactive: all.filter((listing) => listing.status !== "active").length,
      },
    };
  }, [listings, alerts, query, filter]);

  const summary = listings
    ? [
        total != null && total > listings.length
          ? t("{count} of {total} listings", { count: formatNumber(listings.length), total: formatNumber(total) })
          : t("{count} listings", { count: formatNumber(total ?? listings.length) }),
        counts.low_stock ? t("{count} low or out of stock", { count: counts.low_stock }) : "",
        counts.content ? t("{count} need content work", { count: counts.content }) : "",
      ]
        .filter(Boolean)
        .join(" · ")
    : undefined;

  return (
    <div className="ac-reveal flex flex-col gap-4">
      <PageHeader title={t("Catalog")} subtitle={summary}>
        <Button variant="secondary" icon="spark" onClick={() => onAskAssistant(t("Which listings need the most work right now, and why?"))}>
          {t("Ask about the catalog")}
        </Button>
      </PageHeader>

      {failed && !listings ? (
        <Notice>{t("The merchant API isn't reachable, so listings can't load.")}</Notice>
      ) : !listings ? (
        <Skeleton className="h-96" />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2.5">
            <SearchField value={query} onChange={setQuery} placeholder={t("Search by title, ID, or attribute")} label={t("Search listings")} className="min-w-[260px] flex-1 sm:max-w-sm" />
            <Segmented<Filter>
              label={t("Filter listings")}
              value={filter}
              onChange={setFilter}
              options={[
                { id: "all", label: t("All"), count: counts.all },
                { id: "active", label: t("Active"), count: counts.active },
                { id: "low_stock", label: t("Low stock"), count: counts.low_stock },
                { id: "content", label: t("Needs content"), count: counts.content },
                { id: "inactive", label: t("Inactive"), count: counts.inactive },
              ]}
            />
          </div>

          {attention.length === 0 && rest.length === 0 ? (
            <Notice>{t("No listings match.")}</Notice>
          ) : null}

          {attention.length ? (
            <Panel title={t("Needs attention")} subtitle={t("{count} · sold out and low stock first", { count: attention.length })}>
              <ListingTable listings={attention} alerts={alerts} onOpen={setOpenListing} />
            </Panel>
          ) : null}

          {rest.length ? (
            <Panel title={attention.length ? t("Everything else") : t("All listings")} subtitle={formatNumber(rest.length)}>
              <ListingTable listings={rest} alerts={alerts} onOpen={setOpenListing} />
            </Panel>
          ) : null}
        </>
      )}

      {openListing ? (
        <ListingSheet listingId={openListing} alert={alerts.get(openListing)} onClose={() => setOpenListing(null)} onAskAssistant={onAskAssistant} />
      ) : null}
    </div>
  );
}
