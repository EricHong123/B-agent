# ACME Tickets (entertainment)

The entertainment example runs both agents over one ticketing engine: the storefront
maps the room, itemizes the all-in price, holds tickets on a server timer, and stages
checkout, with waitlist, wallet, and transfers on the page; the portal shows each event's
pacing, stages hold releases, price moves, and promotions, and applies them from the
preview card to the seats the storefront sells.

## Run

```bash
python scripts/run_demo.py entertainment               # API :8003 + storefront :3003
python scripts/run_demo.py entertainment --merchant     # API :8003 + portal :3103
python scripts/run_demo.py entertainment --all          # both web apps over one API
```

Or start the pieces yourself, after `npm ci` in `examples/`:

```bash
uvicorn entertainment.api.main:app --app-dir examples --reload --port 8003
(cd examples/entertainment/storefront-web && npm run dev)     # :3003
(cd examples/entertainment/merchant-web && npm run dev)       # :3103
```

Chat needs `ANTHROPIC_API_KEY` in the repo-root `.env` or the environment; browsing the
catalog and the portal's widgets do not. `MERCHANT_REQUIRE_HOST_APPROVAL=0` lets a chat
approval apply a change; by default the preview card's button applies it.

## Try

Storefront (`scripts/smoke_chat.py --vertical entertainment` runs the same three turns):

1. I want two tickets to The Headliner show on the Friday night — somewhere with actual seats, not the pit. What are my tier options, all-in, and where do they put me in the room?
2. Before I commit — break down exactly what the lower bowl price is made of. What's the face value and what are the fees?
3. OK, hold two lower bowl tickets for me while I find my card.

Portal (`scripts/smoke_chat.py --vertical entertainment --merchant`; the third turn is
refused until the change is approved on its card, and the last two follow the approval):

1. How is the Friday Headliner show pacing against comparable events?
2. Release sixty of the promoter-hold seats on the Upper Terrace so they're on sale for the final stretch. Show me the release before it goes live.
3. Good — apply the release.
4. While we're on that tier: tag the Upper Terrace listing 'almost gone' and take its price up 15% for the final push. Stage both and show me before anything goes live.
5. Which shows sold the most tickets this week, and how does each compare with the week before? Put it on a card.

Single prompts, each in a fresh session:

| Surface | Prompt | A good answer |
|---|---|---|
| Storefront | I can't make The Duo show anymore. Can you refund my two GA Floor tickets? | Reads the refunds policy: tickets are refunded only when a show is cancelled or rescheduled, and this one is neither; offers a transfer or a resale listing instead, and refunds nothing itself. |
| Storefront | Is the Synth-Pop Act show really sold out, or is there anything left at all? | Searches live inventory: every box-office tier reads zero remaining, the two fan resale pairs are shown at their all-in prices with the premium over face; points to the event page for the waitlist, and claims no scarcity the counts do not show. |

## What is specific to this example

- `api/ticketing.py`: `TicketingEngine`, shared by both backends: `remaining()` is capacity
  less sold, held, and offered tickets; holds expire after `HOLD_TTL_S`; returns become
  waitlist offers; transfers stay cancellable. It charges nothing.
- `api/mock_ticketing.py`: `MockTicketing`, the `StorefrontBackend`: the cart is the
  session's live holds, `get_disclosure` itemizes the fees, resale rows carry a value score.
- `api/mock_merchant.py`: `MockTicketingMerchant`, the `MerchantBackend` over the same
  engine: stock is the open count, a restock releases held seats through `add_capacity`,
  price moves keep the fee lines fixed, pausing a tier raises `ChangeNotApplicable`.
- `api/venue_map.py`: `present_venue_map`, the room's tiers with live prices and counts.
- `api/hold_view.py`: `present_hold`, the held lines and countdown.
- `api/event_pacing.py`: `present_event_pacing`, sell-through per tier against the
  comparable baseline, hold buckets, waitlist depth.
- `api/agent_config.py`: the two configs: disclosures on, ticketing terms in both lexicons,
  fee lines and face value in `protected_fields`, analysis off.
- `api/main.py`: the holds, waitlist, wallet, transfer, and demo-return routes; engine
  notices reach the agent as app events.
- `api/merchant.py`: the overview's upcoming shows and the `/pacing` read.
- `storefront-web/`, `merchant-web/`: this example's cards, views, and tokens, over `../web-shared/`.

## Data

`data/catalog.json` (no photos), `inventory.json` (capacity and sold per tier),
`venues.json`, `tickets.json` (the wallet), `orders.json`, `policies.json`, `users.json`,
and `memory-seed.json` feed the storefront; `merchant_metrics.json`,
`merchant_pacing.json` (allocations, history, baselines), `merchant_campaigns.json`, and
`merchant_messages.json` feed the portal, whose holds view also reads `venues.json`;
`merchant_returns.json` (refunded and transferred tickets, each with a reason code and the
fan's note) feeds `get_return_reasons`. The
shows are dated as of `dates_anchored_to` in `catalog.json` and move forward by whole weeks
at boot, with the pacing book and the order lines that name them, so they stay ahead of the
clock (`shift_event_dates` in `api/mock_ticketing.py`).

Sessions and identity are the shared host code in [`../demo_common/`](../demo_common/): a
session id stands for a demo profile or the one merchant.
