# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The constraint evaluation of the shopping agent's recommendations. Each case in
``scripts/constraint_cases/<vertical>.yaml`` is one customer message and the hard
constraints it states, run as one turn against the vertical's mock backend at a fixed
clock. Every product the turn presented (in any component) or put in the cart is checked
against the backend's own record, never against the answer text, and scored:

    constraint_violation   a presented or added product breaks a stated constraint, and
                           its card does not mark that miss
    asked_or_declined      for a case nothing in the catalog satisfies: no product is shown
                           as a match, and the turn says nothing fits or asks

The Constraint Violation Rate is cases with a violation over cases. ``docs/metrics.md``
describes the case file and how to read the report.

    python scripts/eval_constraints.py                     # offline, every vertical
    python scripts/eval_constraints.py --vertical retail --failures
    python scripts/eval_constraints.py --mode live         # the provider MODEL_PROVIDER names
    python scripts/eval_constraints.py --no-filters        # ablation: constraints only in words

Offline mode runs the real turn loop, tools, gates, and backends with a scripted
responder in place of the model: it searches with the stated constraints as filters,
retries once without them when nothing comes back, and shows the top results, marking
the retry's results as missing the request. Its numbers show which constraints search
filters alone enforce; live mode measures a model.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT / "scripts"), str(REPO_ROOT / "examples")]

from commerce_common.testing import FakeStream, text_message, tool_use_message  # noqa: E402
from eval_go_live import (  # noqa: E402
    VERTICALS,
    _fenced_json,
    _has,
    _pct,
    agent_setup,
    build_agent,
    load_object,
)
from shopping_agent import ShoppingSessionContext, ShoppingSessionState  # noqa: E402

CASES_DIR = REPO_ROOT / "scripts" / "constraint_cases"
DEFAULT_CLOCK = "2026-10-01T12:00:00+00:00"
PICKS = 3  # how many results the offline responder shows

# The kinds of constraint a product can break; ``stock`` applies to every case.
KINDS = ("price", "option", "date", "stock", "data", "seats")

# Wording on a product's own card that marks it as missing a constraint, per kind, in
# English and Chinese. A product whose card marks every miss it has is flagged, not a
# violation (the system prompt's rule: show such items with the miss marked on each).
MISS_CUES: dict[str, tuple[str, ...]] = {
    "any": (
        "doesn't meet", "does not meet", "doesn't match", "does not match", "misses your",
        "outside your", "not within your", "doesn't fit", "does not fit", "不符合", "不满足",
    ),
    "price": (
        "over budget", "over your", "above your", "exceeds", "more than your", "over the $",
        "超出预算", "超预算", "高于预算", "超过预算",
    ),
    "option": (
        "doesn't come in", "does not come in", "not offered in", "isn't offered in",
        "not available in", "only comes in", "only in ", "没有该", "无此",
    ),
    "date": (
        "arrives after", "after your", "won't arrive", "will not arrive", "not in time",
        "too late", "later than", "not available on", "isn't available on", "other date",
        "晚于", "来不及", "不在您的日期",
    ),
    "stock": (
        "out of stock", "sold out", "unavailable", "not in stock", "waitlist", "缺货", "售罄",
        "无货",
    ),
    "data": ("less data", "smaller allowance", "less than you need", "数据不足"),
    "seats": ("not enough", "only 1 left", "only one left", "座位不足", "余票不足"),
}  # fmt: skip

# Wording that says nothing fits, or that asks; a question mark also counts as asking.
NOTHING_FITS_CUES = (
    "nothing", "none of", "no option", "no match", "couldn't find", "could not find",
    "don't have", "do not have", "don't carry", "doesn't carry", "do not carry",
    "not available", "isn't available", "sold out", "over your budget", "above your budget",
    "没有", "无法", "售罄", "超出预算",
)  # fmt: skip
_DELIVERY_LABEL = re.compile(r"(?P<month>[A-Z][a-z]{2}) (?P<day>\d{1,2})\s*$")


# -- cases --------------------------------------------------------------------------


@dataclass(frozen=True)
class Constraints:
    """The hard constraints a customer stated. ``require`` maps an option, an attribute,
    or a record field (``category``, ``title``) to the value the product must have; a
    record without that field misses it. The date keys each read one vertical's
    record: ``deliver_by`` the delivery promise, ``available_on`` the availability
    window, ``event_on`` and ``event_by`` the event date."""

    max_price: float | None = None
    require: dict[str, str] = field(default_factory=dict)
    deliver_by: date | None = None
    available_on: date | None = None
    event_on: date | None = None
    event_by: date | None = None
    min_data_gb: float | None = None
    min_quantity: int | None = None

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> Constraints:
        unknown = set(entry) - set(inspect.signature(cls).parameters)
        if unknown:
            raise ValueError(f"unknown constraints: {sorted(unknown)}")
        dates = ("deliver_by", "available_on", "event_on", "event_by")
        return cls(
            max_price=entry.get("max_price"),
            require={k: str(v) for k, v in (entry.get("require") or {}).items()},
            min_data_gb=entry.get("min_data_gb"),
            min_quantity=entry.get("min_quantity"),
            **{k: _date(entry.get(k)) for k in dates},
        )


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


@dataclass
class Case:
    id: str
    question: str
    constraints: Constraints
    query: str

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> Case:
        return cls(
            id=entry["id"],
            question=entry["q"],
            constraints=Constraints.from_entry(entry.get("constraints") or {}),
            query=entry["query"],
        )


def load_cases(vertical: str) -> list[Case]:
    entries = yaml.safe_load((CASES_DIR / f"{vertical}.yaml").read_text(encoding="utf-8"))
    cases = [Case.from_entry(entry) for entry in entries["cases"]]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError(f"{vertical}: duplicate case ids")
    return cases


def build_backend(vertical: str, clock: datetime) -> Any:
    """The vertical's mock on the case clock, so its dates (delivery promises, shifted
    availability and event dates) are the same on every run."""
    backend_class = load_object(VERTICALS[vertical].backend)
    parameters = inspect.signature(backend_class).parameters
    if "today" in parameters:
        return backend_class(today=clock.date())
    if "now" in parameters:
        return backend_class(now=lambda: clock)
    return backend_class()


# -- the check ----------------------------------------------------------------------


def broken(record: Any, constraints: Constraints, clock: datetime) -> set[str]:
    """The kinds of constraint one purchasable record breaks, read from its own fields.
    A date or allowance the record does not carry is not held against it."""
    kinds: set[str] = set()
    attributes = {k: str(v) for k, v in record.attributes.items()}
    if constraints.max_price is not None and record.price > constraints.max_price + 0.005:
        kinds.add("price")
    for name, wanted in constraints.require.items():
        if name in record.option_values:
            ok = record.option_values[name].casefold() == wanted.casefold()
        else:
            actual = attributes.get(name, getattr(record, name, None))
            ok = isinstance(actual, str) and wanted.casefold() in actual.casefold()
        if not ok:
            kinds.add("option")
    if not record.in_stock:
        kinds.add("stock")
    promised = promised_date(attributes, clock)
    if constraints.deliver_by and promised and promised > constraints.deliver_by:
        kinds.add("date")
    if constraints.available_on and "availability_from" in attributes:
        first = date.fromisoformat(attributes["availability_from"])
        last = date.fromisoformat(attributes.get("availability_to", "9999-12-31"))
        if not first <= constraints.available_on <= last:
            kinds.add("date")
    if "event_date" in attributes:
        held = date.fromisoformat(attributes["event_date"])
        if (constraints.event_on and held != constraints.event_on) or (
            constraints.event_by and held > constraints.event_by
        ):
            kinds.add("date")
    allowance = attributes.get("data_allowance_gb", "unlimited").strip().lower()
    need = constraints.min_data_gb
    if need is not None and allowance != "unlimited" and float(allowance) < need:
        kinds.add("data")
    remaining = attributes.get("tickets_remaining")
    seats = constraints.min_quantity
    if seats is not None and remaining is not None and int(remaining) < seats:
        kinds.add("seats")
    return kinds


def promised_date(attributes: dict[str, str], clock: datetime) -> date | None:
    """The day in a "Get it by Sat, Oct 3" promise, in the year that puts it on or after
    the clock; None without one."""
    match = _DELIVERY_LABEL.search(attributes.get("delivery", ""))
    if match is None:
        return None
    month = datetime.strptime(match["month"], "%b").month
    promised = date(clock.year, month, int(match["day"]))
    return promised if promised >= clock.date() else promised.replace(year=clock.year + 1)


def marked(card: str) -> set[str]:
    """The kinds of miss a card's own text marks."""
    if _has(card, MISS_CUES["any"]):
        return set(KINDS)
    return {kind for kind in KINDS if _has(card, MISS_CUES[kind])}


@dataclass
class Verdict:
    broken: set[str]
    unmarked: set[str]


def assess(product_id: str, card: str, lookup: Any, case: Case, clock: datetime) -> Verdict | None:
    """One shown or added product against the case. A family is judged by its variant
    that comes closest: fewest unmarked misses, then fewest misses."""
    record = lookup(product_id)
    if record is None:
        return None
    candidates = [lookup(v.product_id) or v for v in getattr(record, "variants", [])] or [record]
    flags = marked(card)
    verdicts = [
        Verdict(kinds, kinds - flags)
        for kinds in (broken(c, case.constraints, clock) for c in candidates)
    ]
    return min(verdicts, key=lambda v: (len(v.unmarked), len(v.broken)))


def fitting(case: Case, backend: Any, clock: datetime) -> list[str]:
    """The listings in the catalog that meet every constraint of the case."""
    return [
        product_id
        for product_id in backend.products
        if not assess(product_id, "", backend.product, case, clock).broken
    ]


# -- the turn -----------------------------------------------------------------------


@dataclass
class Turn:
    answer: str
    tools: list[str]
    shown: dict[str, str]  # product id -> the text on its own card
    added: list[str]  # product ids the cart took


def _is_record(node: dict[str, Any]) -> bool:
    return "title" in node and "price" in node


def _local_text(node: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in node.items():
        if key.endswith("_id"):
            continue
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts += [item for item in value if isinstance(item, str)]
    return " ".join(parts)


def shown_products(payload: Any, out: dict[str, str] | None = None) -> dict[str, str]:
    """Every product a component payload shows, with the text on that product's own card:
    a pick's reason, a comparison entry's pros and cons, a plan step's label and detail.
    A component's title is not on any one card."""
    out = {} if out is None else out

    def walk(node: Any, card: str) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, card)
        elif isinstance(node, dict):
            local = _local_text(node)
            product_id = node.get("product_id")
            if isinstance(product_id, str):
                own = card if _is_record(node) else local
                out[product_id] = f"{out.get(product_id, '')} {own}".strip()
            if _is_record(node):
                return  # a record's variants are not shown products
            for value in node.values():
                walk(value, local)

    walk(payload, "")
    return out


async def run_turn(
    case: Case,
    vertical: str,
    backend: Any,
    *,
    mode: str,
    clock: datetime,
    client: Any,
    config: Any,
    use_filters: bool = True,
) -> Turn:
    responder = client if mode == "live" else FilterBaseline(case, use_filters=use_filters)
    agent = build_agent(vertical, backend, responder, config)
    session = ShoppingSessionContext(session_id=f"eval-{case.id}", user_id="eval", now=clock)
    messages = [{"role": "user", "content": case.question}]
    text: list[str] = []
    turn = Turn("", [], {}, [])
    adds: dict[str, str] = {}
    async for event in agent.stream_turn(messages, session, ShoppingSessionState()):
        data = event.data
        if event.type == "text_delta":
            text.append(data["text"])
        elif event.type == "tool_call":
            turn.tools.append(data["tool"])
            if data["tool"] == "add_to_cart":
                adds[data["id"]] = str((data.get("input") or {}).get("product_id", ""))
        elif event.type == "tool_result" and data["id"] in adds and data.get("status") == "ok":
            turn.added.append(adds.pop(data["id"]))
        elif event.type == "ui" and data["component"] != "suggestions":
            shown_products(data["payload"], turn.shown)
    turn.answer = " ".join(text)
    return turn


class FilterBaseline:
    """The offline stand-in for the model: a ``messages.stream`` client that searches with
    the case's constraints as filters, retries once with the query alone when that comes
    back empty, and shows the top results; the retry's results are marked as missing the
    request, and a second empty search is reported as nothing fitting."""

    def __init__(self, case: Case, *, use_filters: bool = True) -> None:
        self.case = case
        self.use_filters = use_filters
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> FakeStream:
        return FakeStream(self._respond(kwargs))

    def filters(self) -> dict[str, Any] | None:
        c = self.case.constraints
        attributes = {k: v for k, v in c.require.items() if k != "category"}
        if c.available_on:
            attributes["travel_date"] = c.available_on.isoformat()
        if c.event_on:
            attributes["event_date"] = c.event_on.isoformat()
        if c.min_data_gb is not None:
            attributes["min_data_gb"] = f"{c.min_data_gb:g}"
        if c.min_quantity is not None:
            attributes["min_quantity"] = str(c.min_quantity)
        filters: dict[str, Any] = {"max_price": c.max_price} if c.max_price is not None else {}
        if "category" in c.require:
            filters["category"] = c.require["category"]
        if attributes:
            filters["attributes"] = attributes
        return filters or None

    def _respond(self, request: dict[str, Any]) -> SimpleNamespace:
        choice = request.get("tool_choice") or {}
        if choice.get("type") == "tool" and choice.get("name") != "search_products":
            return tool_use_message(choice["name"], {})
        rounds = _results(request["messages"])
        searches = [result for name, result in rounds if name == "search_products"]
        filters = self.filters() if self.use_filters else None
        if not searches:
            return tool_use_message(
                "search_products",
                {"query": self.case.query, **({"filters": filters} if filters else {})},
            )
        found = _search_hits(searches[-1])
        if not found and filters and len(searches) == 1:
            return tool_use_message("search_products", {"query": self.case.query})
        retried = len(searches) > 1
        if found and "present_products" not in {name for name, _ in rounds}:
            reason = "Doesn't meet everything you asked for" if retried else None
            picks = [{"product_id": p, "reason": reason} for p in found[:PICKS]]
            return tool_use_message("present_products", {"picks": picks})
        if not found:
            return text_message("Nothing in the catalog matches that. Want me to widen it?")
        if retried:
            return text_message("Nothing matches all of that; these are the closest.")
        return text_message("These fit what you asked for.")


def _results(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Each tool result of the turn in order, as (tool name, result text)."""
    names: dict[str, str] = {}
    rounds: list[tuple[str, str]] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            block = block if isinstance(block, dict) else block.model_dump()
            if block.get("type") == "tool_use":
                names[block["id"]] = block["name"]
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in names:
                text = block.get("content")
                if isinstance(text, list):
                    text = "".join(part.get("text", "") for part in text)
                rounds.append((names[block["tool_use_id"]], str(text or "")))
    return rounds


def _search_hits(result: str) -> list[str]:
    payload = _fenced_json(result)
    if not isinstance(payload, dict):
        return []
    return [p["product_id"] for p in payload.get("results") or [] if p.get("product_id")]


# -- scoring ------------------------------------------------------------------------


@dataclass
class Score:
    violation: bool
    asked_or_declined: bool | None  # None when something in the catalog fits
    violating: dict[str, list[str]]  # product id -> the kinds it breaks unmarked
    flagged: list[str]
    checked: list[str]


def score(case: Case, turn: Turn, lookup: Any, clock: datetime, *, fits: bool) -> Score:
    """``fits`` says whether anything in the catalog meets every constraint."""
    violating: dict[str, list[str]] = {}
    flagged: list[str] = []
    checked: list[str] = []
    # A product the cart took is judged with no card: a write is never a marked miss.
    cards = {pid: card for pid, card in turn.shown.items()} | dict.fromkeys(turn.added, "")
    for product_id, card in cards.items():
        verdict = assess(product_id, card, lookup, case, clock)
        if verdict is None:
            continue
        checked.append(product_id)
        if verdict.unmarked:
            kinds = set(violating.get(product_id, [])) | verdict.unmarked
            violating[product_id] = sorted(kinds, key=KINDS.index)
        elif verdict.broken:
            flagged.append(product_id)
    declined = None
    if not fits:
        said = _has(turn.answer, NOTHING_FITS_CUES) or "?" in turn.answer or "？" in turn.answer
        declined = not violating and said
    return Score(bool(violating), declined, violating, flagged, checked)


# -- the report ---------------------------------------------------------------------


@dataclass
class Tally:
    cases: int = 0
    violated: int = 0
    items: int = 0
    violating: int = 0
    flagged: int = 0
    nothing_fits: int = 0
    declined: int = 0
    kinds: Counter = field(default_factory=Counter)

    def add(self, result: Score) -> None:
        self.cases += 1
        self.violated += result.violation
        self.items += len(result.checked)
        self.violating += len(result.violating)
        self.flagged += len(result.flagged)
        if result.asked_or_declined is not None:
            self.nothing_fits += 1
            self.declined += result.asked_or_declined
        for kinds in result.violating.values():
            self.kinds.update(kinds)

    def merge(self, other: Tally) -> None:
        for name in ("cases", "violated", "items", "violating", "flagged"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.nothing_fits += other.nothing_fits
        self.declined += other.declined
        self.kinds.update(other.kinds)


def print_table(tallies: dict[str, Tally]) -> None:
    head = ("cases", "violated", "CVR", "items", "violating", "flagged", "asked/declined")
    print(f"\n{'vertical':<16}" + "".join(f"{h:>15}" for h in head))
    for name, t in tallies.items():
        cells = (
            t.cases,
            f"{t.violated}/{t.cases}",
            _pct(t.violated, t.cases),
            t.items,
            f"{t.violating}/{t.items}",
            t.flagged,
            f"{t.declined}/{t.nothing_fits}",
        )
        print(f"{name:<16}" + "".join(f"{c:>15}" for c in cells))


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    verticals = list(VERTICALS) if args.vertical == "all" else [args.vertical]
    clock = datetime.fromisoformat(args.clock)
    by_vertical: dict[str, Tally] = {}
    rows: list[dict[str, Any]] = []
    for vertical in verticals:
        client, config = agent_setup(vertical, args.mode)
        tally = by_vertical.setdefault(vertical, Tally())
        for case in load_cases(vertical)[: args.limit or None]:
            backend = build_backend(vertical, clock)
            turn = await run_turn(
                case,
                vertical,
                backend,
                mode=args.mode,
                clock=clock,
                client=client,
                config=config,
                use_filters=not args.no_filters,
            )
            fits = fitting(case, backend, clock)
            result = score(case, turn, backend.product, clock, fits=bool(fits))
            tally.add(result)
            row = {"vertical": vertical, "id": case.id, "fits": fits, **result.__dict__}
            rows.append(row | {"answer": turn.answer})
            failed = result.violation or result.asked_or_declined is False
            if args.failures and failed:
                print(f"  ✗ {vertical}/{case.id} violating={result.violating} {turn.answer!r}")
    total = Tally()
    for tally in by_vertical.values():
        total.merge(tally)
    return {"by_vertical": by_vertical, "total": total, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vertical", choices=["all", *VERTICALS], default="all")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--clock", default=DEFAULT_CLOCK, help="ISO time the mocks run at")
    parser.add_argument("--limit", type=int, default=0, help="first N cases per vertical")
    parser.add_argument(
        "--no-filters", action="store_true", help="ablation: the offline search sets no filters"
    )
    parser.add_argument("--failures", action="store_true", help="print each failing case")
    parser.add_argument("--json", type=Path, help="write per-case results here")
    args = parser.parse_args()

    responder = "filter baseline" if args.mode == "offline" else "live model"
    filters = "filters off (ablation)" if args.no_filters else "filters on"
    print(f"constraint eval · {args.mode} ({responder}) · {filters} · clock {args.clock}")
    result = asyncio.run(evaluate(args))
    total: Tally = result["total"]
    print_table({**result["by_vertical"], "total": total})
    kinds = " · ".join(f"{k} {total.kinds[k]}" for k in KINDS if total.kinds[k])
    print(
        f"\nConstraint Violation Rate  {total.violated}/{total.cases} = "
        f"{_pct(total.violated, total.cases)}   (cases showing or adding an unmarked miss)"
        f"\nviolating items by constraint: {kinds or 'none'}"
    )
    if args.json:
        args.json.write_text(
            json.dumps(result["rows"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
