# ACME Mobile (telecom)

The telecom example runs both agents over one carrier catalog: the storefront compares
plans in a matrix, answers upgrade questions from the signed-in account, shows a plan's
service facts before it goes in the cart, and stages checkout; the portal reads churn,
shows the subscriber base per plan, stages plan price moves that state how many lines they
touch, and applies them from the preview card.

## Run

```bash
python scripts/run_demo.py telecom               # API :8002 + storefront :3002
python scripts/run_demo.py telecom --merchant     # API :8002 + portal :3102
python scripts/run_demo.py telecom --all          # both web apps over one API
```

Or start the pieces yourself, after `npm ci` in `examples/`:

```bash
uvicorn telecom.api.main:app --app-dir examples --reload --port 8002
(cd examples/telecom/storefront-web && npm run dev)     # :3002
(cd examples/telecom/merchant-web && npm run dev)       # :3102
```

Chat needs `ANTHROPIC_API_KEY` in the repo-root `.env` or the environment; browsing the
catalog and the portal's widgets do not. `MERCHANT_REQUIRE_HOST_APPROVAL=0` lets a chat
approval apply a change; by default the preview card's button applies it.

## Try

Storefront (`scripts/smoke_chat.py --vertical telecom` runs the same three turns):

1. I keep blowing through my data — I've bought top-ups three months running. What plans would actually fit around 15GB a month? Show them side by side.
2. Am I eligible to upgrade my ACME Phone 4 yet? Show me what I could move to, and what the trade-in credit and early-upgrade terms would get me.
3. Switch me to the Unlimited plan and put it in my cart — and confirm there's no fee for changing plans mid-cycle.

Portal (`scripts/smoke_chat.py --vertical telecom --merchant`; the third turn is refused
until the change is approved on its card, and the last two follow the approval):

1. Show me churn by plan across the base. Which plan is bleeding, and since when?
2. Put a retention offer in front of the Essential lines that keep buying top-ups: a month of Plus 15GB at the Essential price if they move up. Stage it as a campaign to that cohort, app push, $1,500. Show me the draft before anything goes out.
3. That's fine — apply it.
4. Stock check while I'm here. Whatever device the alerts are flagging, stage a restock sized from its sell-through so we're covered for the next month. Preview first.
5. Where did last week's net adds come from against the week before? Put gross adds, deacts, port-ins and port-outs on one card and tell me what moved.

Single prompts, each in a fresh session:

| Surface | Prompt | A good answer |
|---|---|---|
| Storefront | If the ACME Phone 3 I ordered isn't for me, how long do I have to send it back, and what would it cost me? | Reads the order and the returns policy: the phone has not arrived, so the 14-day window starts on delivery; names the restocking fee and that used prepaid service is not refunded. It does not open a return. |
| Storefront | Add a Roaming Day Pass to my cart for my trip next week. | Finds the pass and adds it (one search, one add), and says a pass covers one day from first use, so a longer trip needs one per day. |
| Portal | Cut the Plus 15GB plan to $39 to stop the churn. Show me what it touches. | Reads the pricing context: $39 is a 22% move, past the per-change limit, so it is not staged; offers $40 as the nearest permanent price or $39 as a date-bound promotion, with the lines and per-line margin the plan carries. |

## What is specific to this example

- `api/mock_telecom.py`: `MockTelecom`, the `StorefrontBackend` over the fixtures, plus
  the account context the agent reads every turn (`get_account_context`: upgrade
  eligibility, trade-in, bill) and the service facts behind `present_disclosure`
  (`get_disclosure`).
- `api/mock_merchant.py`: `MockTelecomMerchant`, the `MerchantBackend` over the same
  `MockTelecom`. A plan's `stock` is its active lines, which `stage_price_update` and
  `stage_promotion` put in `guardrail_notes`; a plan restock raises `ChangeNotApplicable`;
  applied changes write back to the storefront.
- `api/plan_matrix.py`: registers `present_plan_comparison` on the storefront; every cell
  is filled from products the session has seen, plus the subscriber's plan and usage.
- `api/plan_mix.py`: registers `present_plan_mix` on the portal from `plan_mix_rows`.
- `api/agent_config.py`: the two configs. The shopping one turns on `enable_disclosures`
  and extends `policy_intent_terms`; the merchant one extends `metrics_intent_terms` and
  puts the regulated fee fields in `protected_fields`.
- `api/main.py`: two demo profiles (subscriber `demo-user`, prospect `demo-user-2`),
  in-process memory seeded from `data/memory-seed.json`, the add-to-cart button route
  (devices and add-ons only), and `GET /api/account` for the storefront chrome.
- `api/merchant.py`: the overview's `today_snapshot` and the portal's `/base` read.
- `storefront-web/`, `merchant-web/`: this example's cards, views, and tokens, over `../web-shared/`.

## Data

`data/catalog.json`, `users.json`, `orders.json`, `policies.json`, and `memory-seed.json`
feed the storefront; `merchant_metrics.json` (daily base motion), `merchant_subscribers.json`
(weekly series per plan, rate card, cohorts), `merchant_inventory.json` (device stock),
`merchant_campaigns.json`, and `merchant_messages.json` feed the portal;
`merchant_returns.json` (device returns and cancelled lines, each with a reason code and the
customer's note) feeds `get_return_reasons`.

Sessions and identity are the shared host code in [`../demo_common/`](../demo_common/): a
session id stands for a demo profile or the one merchant.
