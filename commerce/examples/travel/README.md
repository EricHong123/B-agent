# ACME Travel (travel)

The travel example runs both agents over one date-bound catalog of stays, flights, and
experiences: the storefront quotes dated searches, lays a trip out day by day, and books
the planned nights; the portal shows the supplier's weekly occupancy calendar, stages
rate moves for a date window, and applies them from the preview card.

## Run

```bash
python scripts/run_demo.py travel               # API :8001 + storefront :3001
python scripts/run_demo.py travel --merchant     # API :8001 + portal :3101
python scripts/run_demo.py travel --all          # both web apps over one API
```

Or start the pieces yourself, after `npm ci` in `examples/`:

```bash
uvicorn travel.api.main:app --app-dir examples --reload --port 8001
(cd examples/travel/storefront-web && npm run dev)     # :3001
(cd examples/travel/merchant-web && npm run dev)       # :3101
```

Chat needs `ANTHROPIC_API_KEY` in the repo-root `.env` or the environment; browsing the
catalog and the portal's widgets do not. `MERCHANT_REQUIRE_HOST_APPROVAL=0` lets a chat
approval apply a change; by default the preview card's button applies it.

## Try

Storefront (`scripts/smoke_chat.py --vertical travel` runs the same three turns):

1. Plan me a long weekend in Lisbon in mid-October — boutique stay, a couple of experiences, walkable neighborhood. Lay it out day by day.
2. Compare the stay you picked against a refundable alternative — what's the price difference for flexibility?
3. Add the refundable stay to my trip, and what does ACME Travel's cancellation window look like for it?

Portal (`scripts/smoke_chat.py --vertical travel --merchant`; the third turn is refused
until the change is approved on its card, and the last two follow the approval):

1. Home says two stays are pacing soft. Which two, how does their October look on the calendar, and where should rates move?
2. Ease the midweek rates by about ten percent on the two softest properties, but only for their soft October weeks. The rest of the calendar stays where it is. Show me the impact before anything goes live.
3. That works — approve it.
4. Now draft a shoulder-season campaign for those same two properties to go with the rate move: email to past guests, a modest budget of around $600. Stage it as a draft so I can read it first.
5. Which of our listings are losing us bookings on the page itself? If a description is thin, tell me which one; if the pages are fine, say so and tell me where the gap really is.

Single prompts, each in a fresh session:

| Surface | Prompt | A good answer |
|---|---|---|
| Storefront | Show me refundable stays in Lisbon under $300 a night. | One search and one card: the Graca suite is the only Lisbon stay that is both refundable and under $300; the Alfama and Baixa guesthouses match the price but are non-refundable, and the answer says so. |
| Storefront | Two of us have $1,500 all-in for Lisbon: the nonstop from New York, three nights somewhere central, and one evening out. Does that work, and what would you book? | Lays out flights for two, three nights, and one evening as a plan, adds it up, says the total lands just over $1,500 and by how much, and offers the swap that closes the gap. |
| Portal | Take the Baixa guesthouse's base rate down to $89 for the shoulder season. | Reads the pricing context: $89 is a 29% move, past the per-change limit, so it is not staged; offers the lowest base rate the limit allows, or $89 as a date-bound promotion on the soft weeks. |

## What is specific to this example

- `api/mock_travel.py`: `MockTravel`, the `StorefrontBackend` over the fixtures. A
  `travel_date` filter is enforced as availability; a dated result is a quote:
  `free_cancellation_until` if refundable, a `date_flex` rate strip, and
  `units_left_for_dates` when three or fewer rooms remain. A stay's first `add_to_cart`
  books the itinerary's planned nights (`TripPlan`).
- `api/mock_merchant.py`: `MockTravelMerchant`, the `MerchantBackend` for the occupancy
  fixture's stays, over the same `MockTravel`. `stage_promotion` is a nightly-rate move
  for a date window, applied as a rate override; `stage_price_update` moves the base rate,
  which is the catalog price. Analysis is off.
- `api/itinerary.py`: registers `present_itinerary`; each day is filled from products the
  session has seen, and the night structure is recorded through `note_trip_plan`.
- `api/occupancy.py`: registers `present_occupancy_calendar`; the agent names stays and a
  window; every figure comes from `get_occupancy_calendar`.
- `api/agent_config.py`: the two configs. The shopping one asks for `travel_date` on dated
  searches; the merchant one adds occupancy terms to `metrics_intent_terms` and
  `nightly_rate` to `price_bearing_fields` and `listing_update_blocked_fields`.
- `api/main.py`: the storefront host with the itinerary extension and an
  `InMemoryMemoryStore` that `MemorySeeder` refills from `data/memory-seed.json` on boot.
- `api/merchant.py`: the `today` block on `/overview` and the `/occupancy` read.
- `storefront-web/`, `merchant-web/`: this example's cards, views, and tokens, over `../web-shared/`.

## Data

`data/catalog.json`, `users.json`, `orders.json`, `policies.json`, and `memory-seed.json`
feed the storefront; `merchant_metrics.json`, `merchant_campaigns.json`, and
`merchant_messages.json` feed the portal; `merchant_occupancy.json` feeds both: the
portal's calendar and the storefront's remaining-rooms count. `merchant_returns.json`
(cancelled bookings with a reason code and the traveller's note) feeds `get_return_reasons`.
The catalog has no photos.

Sessions and identity are the shared host code in [`../demo_common/`](../demo_common/): a
session id stands for a demo profile or the one merchant.
