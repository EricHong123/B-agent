# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""A scripted live conversation against one vertical example API, in-process or against a
running server, asserting that each turn calls the expected tools and emits the expected
events. Merchant arcs also assert the approval gate: a chat approval applies nothing, the
arc then approves through the portal endpoint, and any later turns run against the applied
state. A vertical may add deterministic checks that run after its conversation
(``POST_CHECKS``).

    python scripts/smoke_chat.py [--vertical travel] [--url http://localhost:8001]
    python scripts/smoke_chat.py --merchant [--arc trend]

Needs Anthropic credentials; each run costs a few cents.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

SESSION_HEADER = "X-Session-Id"

# Storefront conversations, one per vertical.
VERTICAL_TURNS: dict[str, list[dict[str, Any]]] = {
    "retail": [
        {
            "message": (
                "I'm taking my partner and our 6-year-old camping for the first time next month. "
                "We need a tent — nothing too heavy to deal with, ideally under $250."
            ),
            "expect_tools": {"search_products"},
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": "Compare the top two options for me — mostly care about space and ease of setup.",
            "expect_tools": set(),
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": "The family one sounds right. Add it to my cart, and remind me what returns look like just in case.",
            "expect_tools": {"add_to_cart"},
            "expect_events": {"cart_update", "turn_complete"},
        },
    ],
    "travel": [
        {
            "message": (
                "Plan me a long weekend in Lisbon in mid-October — boutique stay, a couple of "
                "experiences, walkable neighborhood. Lay it out day by day."
            ),
            "expect_tools": {"search_products"},
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": "Compare the stay you picked against a refundable alternative — what's the price difference for flexibility?",
            "expect_tools": set(),
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": "Add the refundable stay to my trip, and what does ACME Travel's cancellation window look like for it?",
            "expect_tools": {"add_to_cart"},
            "expect_events": {"cart_update", "turn_complete"},
        },
    ],
    "telecom": [
        {
            "message": (
                "I keep blowing through my data — I've bought top-ups three months running. "
                "What plans would actually fit around 15GB a month? Show them side by side."
            ),
            "expect_tools": {"search_products"},
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": (
                "Am I eligible to upgrade my ACME Phone 4 yet? Show me what I could move "
                "to, and what the trade-in credit and early-upgrade terms would get me."
            ),
            "expect_tools": {"search_policies"},
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": (
                "Switch me to the Unlimited plan and put it in my cart — and confirm "
                "there's no fee for changing plans mid-cycle."
            ),
            "expect_tools": {"add_to_cart"},
            "expect_events": {"cart_update", "turn_complete"},
        },
    ],
    "entertainment": [
        {
            "message": (
                "I want two tickets to The Headliner show on the Friday night — "
                "somewhere with actual seats, not the pit. What are my tier options, "
                "all-in, and where do they put me in the room?"
            ),
            "expect_tools": {"search_products"},
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": (
                "Before I commit — break down exactly what the lower bowl price is made "
                "of. What's the face value and what are the fees?"
            ),
            "expect_tools": {"present_disclosure"},
            "expect_events": {"ui", "turn_complete"},
        },
        {
            "message": "OK, hold two lower bowl tickets for me while I find my card.",
            "expect_tools": {"add_to_cart"},
            "expect_events": {"cart_update", "turn_complete"},
        },
    ],
}

VERTICAL_APPS = {
    "retail": "retail.api.main",
    "travel": "travel.api.main",
    "telecom": "telecom.api.main",
    "entertainment": "entertainment.api.main",
}

# Merchant arcs, one or more per vertical. A ``portal_approve_kind`` step approves the
# most recently staged change of that kind through the portal endpoint.
MERCHANT_TURNS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "retail": {
        # The morning briefing, a restock with a listing fix, then after the approval a
        # trend check and the fortnight's sales drivers.
        "morning": [
            {
                "message": "What needs my attention this morning?",
                "expect_tools": {"get_business_snapshot"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Restock the ocean wall decals with enough to cover the next month at the "
                    "current pace, and fix that listing's description so it covers what's been "
                    "missing. Show me both before anything goes live."
                ),
                "expect_tools": {"stage_inventory_action"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": "Looks right — approve the restock.",
                "expect_tools": {"apply_change"},
                "expect_events": {"turn_complete"},
                "forbid_applied_change": True,
            },
            {"portal_approve_kind": "inventory_action"},
            {
                "message": (
                    "Kids-room decor feels like it's having a moment. Pull the numbers — is the "
                    "under-the-sea line really outperforming the rest of the store this month?"
                ),
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"stage_price_update", "stage_promotion", "apply_change"},
            },
            {
                "message": (
                    "Why did sales move over the last two weeks — which category or listings "
                    "drove it, and by how much?"
                ),
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"stage_price_update", "stage_promotion", "apply_change"},
            },
        ],
        # A promotion and a listing refresh, margin impact first.
        "trend": [
            {
                "message": (
                    "The ocean-room collection looks like it's trending — how is it actually "
                    "doing compared to the rest of the store this month?"
                ),
                "expect_tools": {"get_business_snapshot"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Set up a weekend promotion on the three best-selling ocean-room listings "
                    "and refresh their titles so they're easier to find. Show me the margin "
                    "impact before anything goes live."
                ),
                "expect_tools": {"stage_promotion"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": "The promotion looks right — approve it. Hold the title changes for now.",
                "expect_tools": {"apply_change"},
                "expect_events": {"turn_complete"},
                "forbid_applied_change": True,
            },
            {"portal_approve_kind": "promotion"},
        ],
    },
    "travel": {
        # The soft stays on the occupancy calendar and a date-bound rate move; after the
        # approval, a campaign draft for the same stays and a listing-content check.
        "pacing": [
            {
                "message": (
                    "Home says two stays are pacing soft. Which two, how does their October look "
                    "on the calendar, and where should rates move?"
                ),
                "expect_tools": {"get_inventory_alerts", "present_occupancy_calendar"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Ease the midweek rates by about ten percent on the two softest properties, "
                    "but only for their soft October weeks. The rest of the calendar stays where "
                    "it is. Show me the impact before anything goes live."
                ),
                "expect_tools": {"stage_promotion"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": "That works — approve it.",
                "expect_tools": {"apply_change"},
                "expect_events": {"turn_complete"},
                "forbid_applied_change": True,
            },
            {"portal_approve_kind": "promotion"},
            {
                "message": (
                    "Now draft a shoulder-season campaign for those same two properties to go "
                    "with the rate move: email to past guests, a modest budget of around $600. "
                    "Stage it as a draft so I can read it first."
                ),
                "expect_tools": {"stage_campaign"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Which of our listings are losing us bookings on the page itself? If a "
                    "description is thin, tell me which one; if the pages are fine, say so and "
                    "tell me where the gap really is."
                ),
                "expect_tools": {"search_listings"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"stage_listing_update", "apply_change"},
            },
        ],
    },
    "telecom": {
        # Churn per plan, a cohort retention campaign, then after the approval a device
        # restock and the week's base motion decomposed.
        "churn": [
            {
                "message": "Show me churn by plan across the base. Which plan is bleeding, and since when?",
                "expect_tools": {"get_business_snapshot"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Put a retention offer in front of the Essential lines that keep buying "
                    "top-ups: a month of Plus 15GB at the Essential price if they move up. Stage "
                    "it as a campaign to that cohort, app push, $1,500. Show me the draft before "
                    "anything goes out."
                ),
                "expect_tools": {"stage_campaign"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": "That's fine — apply it.",
                "expect_tools": {"apply_change"},
                "expect_events": {"turn_complete"},
                "forbid_applied_change": True,
            },
            {"portal_approve_kind": "campaign"},
            {
                "message": (
                    "Stock check while I'm here. Whatever device the alerts are flagging, stage a "
                    "restock sized from its sell-through so we're covered for the next month. "
                    "Preview first."
                ),
                "expect_tools": {"get_inventory_alerts", "stage_inventory_action"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Where did last week's net adds come from against the week before? Put gross "
                    "adds, deacts, port-ins and port-outs on one card and tell me what moved."
                ),
                "expect_tools": {"query_metrics", "present_metrics"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
        ],
        # Campaign performance and a staged cohort campaign.
        "retention": [
            {
                "message": "How is the contract-end save campaign performing so far?",
                "expect_tools": {"get_campaign_performance"},
                "expect_events": {"turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Draft a win-back campaign for the lines we lost in the last 90 days — "
                    "$1,500 budget, email channel. Show me the draft before anything goes live."
                ),
                "expect_tools": {"stage_campaign"},
                "expect_events": {"change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": "Send it — approve.",
                "expect_tools": {"apply_change"},
                "expect_events": {"turn_complete"},
                "forbid_applied_change": True,
            },
            {"portal_approve_kind": "campaign"},
        ],
    },
    "entertainment": {
        # The event-pacing panel and a hold release that puts seats on sale; after the
        # approval, a scarcity tag the counts do not support beside a price move they do,
        # then the week's tickets per show.
        "pacing": [
            {
                "message": ("How is the Friday Headliner show pacing against comparable events?"),
                "expect_tools": {"present_event_pacing"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": (
                    "Release sixty of the promoter-hold seats on the Upper Terrace so they're "
                    "on sale for the final stretch. Show me the release before it goes live."
                ),
                "expect_tools": {"stage_inventory_action"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
            {
                "message": "Good — apply the release.",
                "expect_tools": {"apply_change"},
                "expect_events": {"turn_complete"},
                "forbid_applied_change": True,
            },
            {
                "portal_approve_kind": "inventory_action",
                # The release must add sellable capacity to the engine.
                "expect_stock_increase": "AT-TIX-101-TER",
            },
            {
                "message": (
                    "While we're on that tier: tag the Upper Terrace listing 'almost gone' and "
                    "take its price up 15% for the final push. Stage both and show me before "
                    "anything goes live."
                ),
                "expect_tools": {"get_pricing_context", "stage_price_update"},
                "expect_events": {"ui", "change_update", "turn_complete"},
                "forbid_tools": {"stage_listing_update", "apply_change"},
            },
            {
                "message": (
                    "Which shows sold the most tickets this week, and how does each compare with "
                    "the week before? Put it on a card."
                ),
                "expect_tools": {"query_metrics", "present_metrics"},
                "expect_events": {"ui", "turn_complete"},
                "forbid_tools": {"apply_change"},
            },
        ],
    },
}
Headers = dict[str, str]
PostCheck = Callable[[httpx.AsyncClient, Headers, Any | None], Awaitable[list[str]]]


async def start_session(
    client: httpx.AsyncClient, *, merchant: bool, user_id: str = "demo-user"
) -> Headers:
    """Mint a token for the role and return the header every later request carries."""
    if merchant:
        response = await client.post("/api/merchant/session")
    else:
        response = await client.post("/api/session", json={"user_id": user_id})
    response.raise_for_status()
    return {SESSION_HEADER: response.json()["session_id"]}


HOLD_TTL_S = 480  # entertainment.api.ticketing.HOLD_TTL_S


async def entertainment_checks(
    client: httpx.AsyncClient, mine: Headers, app_module: Any | None
) -> list[str]:
    """After the storefront arc: the hold it placed is real and counts down; in-process,
    rewinding its expiry through the engine clock empties the cart and returns the seats;
    transfers refuse fabricated ids, other fans, and missing tokens, and the owner's own
    transfer stages and cancels. Against --url the expiry step is skipped."""
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    async def remaining(product_id: str) -> int:
        product = (await client.get(f"/api/products/{product_id}")).json()
        return int(product["attributes"]["tickets_remaining"])

    holds = (await client.get("/api/holds", headers=mine)).json()["holds"]
    if not holds:
        return ["the conversation left no live hold"]
    hold = holds[0]
    print(
        f"    hold {hold['hold_id']}: {hold['quantity']} x {hold['product_id']}, {hold['seconds_remaining']}s left"
    )
    expect(
        0 < hold["seconds_remaining"] <= HOLD_TTL_S,
        f"hold countdown outside the TTL: {hold['seconds_remaining']}s",
    )
    before = await remaining(hold["product_id"])

    if app_module is None:
        print("    --url mode: hold expiry is not asserted against a remote clock")
        for live in holds:
            release = await client.post(
                "/api/holds/release", json={"hold_id": live["hold_id"]}, headers=mine
            )
            expect(
                release.status_code == 200,
                f"owner could not release hold {live['hold_id']}: {release.status_code}",
            )
    else:
        engine = app_module.engine
        for live in engine.holds_for_session(mine[SESSION_HEADER]):
            live.expires_at = engine.now() - timedelta(seconds=1)
        cart = (await client.get("/api/cart", headers=mine)).json()
        expect(not cart["holds"] and not cart["items"], "an expired hold is still on the cart")
        after = await remaining(hold["product_id"])
        expect(
            after == before + hold["quantity"],
            f"expiry returned {after - before} seats, expected {hold['quantity']}",
        )
        print(f"    hold expiry: remaining {before} -> {after}")

    wallet = (await client.get("/api/tickets", headers=mine)).json()["tickets"]
    active = [ticket["ticket_id"] for ticket in wallet if ticket["status"] == "active"]
    if not active:
        return [*failures, "no active wallet tickets to drive the transfer gates with"]

    async def transfer(ticket_ids: list[str], headers: Headers) -> httpx.Response:
        body = {"ticket_ids": ticket_ids, "recipient": "Rowan"}
        return await client.post("/api/tickets/transfer", json=body, headers=headers)

    async def status_of(ticket_id: str) -> str:
        tickets = (await client.get("/api/tickets", headers=mine)).json()["tickets"]
        return next(ticket["status"] for ticket in tickets if ticket["ticket_id"] == ticket_id)

    expect(
        (await transfer(["AT-TKT-0000"], mine)).status_code == 404,
        "a fabricated ticket id was not refused",
    )
    expect(
        (await transfer([active[0], "AT-TKT-0000"], mine)).status_code == 404,
        "a mixed batch was not refused",
    )
    expect(
        await status_of(active[0]) == "active",
        "a refused mixed batch still staged the owned ticket",
    )
    intruder = await start_session(client, merchant=False, user_id="demo-user-2")
    expect(
        (await transfer([active[0]], intruder)).status_code == 403,
        "another fan's session could transfer this ticket",
    )
    expect(
        (await transfer([active[0]], {})).status_code == 401,
        "a request without a token was not refused",
    )
    staged = await transfer([active[-1]], mine)
    expect(staged.status_code == 200, f"the owner's own transfer was refused: {staged.status_code}")
    if staged.status_code == 200:
        transfer_id = staged.json()["transfer"]["transfer_id"]
        cancel = await client.post(
            "/api/tickets/transfer/cancel", json={"transfer_id": transfer_id}, headers=mine
        )
        expect(cancel.status_code == 200, f"cancel refused: {cancel.status_code}")
        expect(
            await status_of(active[-1]) == "active", "a cancelled transfer left the ticket pending"
        )
    if not failures:
        print(
            "    transfer gates hold: 404 fabricated, 403 other fan, 401 no token, own stage and cancel"
        )
    return failures


# Deterministic checks a vertical runs after its storefront conversation.
POST_CHECKS: dict[str, PostCheck] = {"entertainment": entertainment_checks}


async def run_turn(
    client: httpx.AsyncClient, headers: Headers, message: str, *, merchant: bool
) -> list[dict[str, Any]]:
    path = "/api/merchant/chat" if merchant else "/api/chat"
    events: list[dict[str, Any]] = []
    async with client.stream(
        "POST", path, json={"message": message}, headers=headers, timeout=180.0
    ) as response:
        response.raise_for_status()
        current_event: str | None = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                current_event = line.removeprefix("event: ").strip()
            elif line.startswith("data: ") and current_event:
                events.append(
                    {"type": current_event, "data": json.loads(line.removeprefix("data: "))}
                )
    return events


def summarize(events: list[dict[str, Any]]) -> str:
    text = "".join(e["data"].get("text", "") for e in events if e["type"] == "text_delta")
    tools = [e["data"]["tool"] for e in events if e["type"] == "tool_call"]
    uis = [e["data"]["component"] for e in events if e["type"] == "ui"]
    usage = next((e["data"].get("usage", {}) for e in events if e["type"] == "turn_complete"), {})
    return (
        f"    tools: {tools or '-'}\n"
        f"    ui:    {uis or '-'}\n"
        f"    text:  {len(text)} chars | tokens in/out: "
        f"{usage.get('input_tokens', '?')}/{usage.get('output_tokens', '?')} "
        f"(cache read {usage.get('cache_read_input_tokens', '?')})"
    )


def check(events: list[dict[str, Any]], turn: dict[str, Any]) -> list[str]:
    failures = []
    seen_tools = {e["data"]["tool"] for e in events if e["type"] == "tool_call"}
    seen_types = {e["type"] for e in events}
    for tool in turn.get("expect_tools", set()):
        if tool not in seen_tools:
            failures.append(f"expected a {tool} call, saw {sorted(seen_tools) or 'none'}")
    for event_type in turn.get("expect_events", set()):
        if event_type not in seen_types:
            failures.append(f"expected a {event_type} event, saw {sorted(seen_types)}")
    for tool in turn.get("forbid_tools", set()):
        if tool in seen_tools:
            failures.append(f"{tool} must not be called on this turn")
    applied = [
        e
        for e in events
        if e["type"] == "change_update"
        and (e["data"].get("change") or {}).get("status") == "applied"
    ]
    if turn.get("forbid_applied_change") and applied:
        failures.append(
            "a change applied from the chat approval; host approval should have refused it"
        )
    if any(e["type"] == "error" for e in events):
        failures.append("turn emitted an error event")
    return failures


async def listing_stock(client: httpx.AsyncClient, headers: Headers, listing_id: str) -> int | None:
    response = await client.get(f"/api/merchant/listings/{listing_id}", headers=headers)
    if response.status_code != 200:
        return None
    return (response.json().get("listing") or {}).get("stock")


async def portal_step(
    client: httpx.AsyncClient, headers: Headers, staged: list[dict[str, Any]], step: dict[str, Any]
) -> list[str]:
    """Approve the newest staged change of the step's kind through the portal endpoint;
    with ``expect_stock_increase`` set, the named listing's stock must grow as a result."""
    kind = step["portal_approve_kind"]
    change = next(
        (c for c in reversed(staged) if c.get("kind") == kind and c.get("status") == "staged"), None
    )
    if change is None:
        seen = [(c.get("kind"), c.get("status")) for c in staged]
        return [f"no staged {kind} change to approve; changes seen: {seen or 'none'}"]
    watched = step.get("expect_stock_increase")
    before = await listing_stock(client, headers, watched) if watched else None
    response = await client.post(
        f"/api/merchant/changes/{change['change_id']}/apply", headers=headers, timeout=60.0
    )
    if response.status_code != 200:
        return [
            f"portal approve of {change['change_id']} failed: {response.status_code} {response.text[:200]}"
        ]
    status = ((response.json() or {}).get("change") or {}).get("status")
    if status != "applied":
        return [f"portal approve returned status {status!r}, expected 'applied'"]
    print(f"    applied {change['change_id']} ({kind}) through the portal")
    if watched:
        after = await listing_stock(client, headers, watched)
        if before is None or after is None or after <= before:
            return [f"{watched} stock did not grow after the apply ({before} -> {after})"]
        print(f"    {watched} stock {before} -> {after}")
    return []


async def run_smoke(args: argparse.Namespace, app_module: Any | None) -> int:
    if app_module is None:
        client = httpx.AsyncClient(base_url=args.url)
    else:
        # The demo APIs answer only to loopback host names.
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_module.app), base_url="http://localhost"
        )
    turns = (
        MERCHANT_TURNS[args.vertical][args.arc] if args.merchant else VERTICAL_TURNS[args.vertical]
    )
    staged: list[dict[str, Any]] = []
    ok = True
    async with client:
        headers = await start_session(client, merchant=args.merchant)
        for index, turn in enumerate(turns, start=1):
            if "portal_approve_kind" in turn:
                print(
                    f"\n[{index}/{len(turns)}] portal: approve the staged {turn['portal_approve_kind']}"
                )
                failures = await portal_step(client, headers, staged, turn)
            else:
                print(f"\n[{index}/{len(turns)}] user: {turn['message'][:80]}...")
                started = time.perf_counter()
                events = await run_turn(client, headers, turn["message"], merchant=args.merchant)
                print(f"    {len(events)} events in {time.perf_counter() - started:.1f}s")
                print(summarize(events))
                staged.extend(
                    change
                    for event in events
                    if event["type"] == "change_update" and (change := event["data"].get("change"))
                )
                failures = check(events, turn)
            for failure in failures:
                print(f"    FAIL: {failure}")
            ok = ok and not failures
        post_check = None if args.merchant else POST_CHECKS.get(args.vertical)
        if post_check is not None:
            print(f"\n[{post_check.__name__}]")
            failures = await post_check(client, headers, app_module)
            for failure in failures:
                print(f"    FAIL: {failure}")
            ok = ok and not failures
    print("\nSMOKE", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", help="base URL of a running demo API; in-process when omitted")
    parser.add_argument(
        "--vertical",
        default="retail",
        choices=sorted(VERTICAL_TURNS),
        help="which example to drive",
    )
    parser.add_argument(
        "--merchant",
        action="store_true",
        help="run a merchant arc instead of the storefront conversation",
    )
    parser.add_argument("--arc", help="which merchant arc; defaults to the vertical's first")
    args = parser.parse_args()
    if args.merchant:
        arcs = MERCHANT_TURNS[args.vertical]
        args.arc = args.arc or next(iter(arcs))
        if args.arc not in arcs:
            parser.error(
                f"the {args.vertical} merchant smoke has no {args.arc!r} arc (has: {', '.join(arcs)})"
            )
    # In-process apps are imported before the event loop starts: the example mains seed
    # memory with asyncio.run() at import time.
    app_module = None if args.url else importlib.import_module(VERTICAL_APPS[args.vertical])
    return asyncio.run(run_smoke(args, app_module))


if __name__ == "__main__":
    sys.exit(main())
