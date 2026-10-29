# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The terms gate: which version of a source passes at the session clock, what the model
and the host's trace hear about the rest, and the cards that cite terms."""

from datetime import UTC, datetime

import pytest

from commerce_common.memory import InMemoryMemoryStore
from shopping_agent import Disclosure, DisclosureRow, Policy, ShoppingSessionContext
from shopping_agent.executor import ShoppingToolExecutor, build_memory
from shopping_agent.gates import (
    CONFLICT,
    CURRENT,
    EXPIRED,
    NOT_IN_FORCE,
    PROVENANCE_GATE,
    SCHEDULED,
    SUPERSEDED,
    TERMS_GATE,
    check_terms,
)

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def passage(policy_id: str, version: str, effective: str, expires: str | None = None, **extra):
    return Policy(
        policy_id=policy_id,
        title="Returns",
        category="returns",
        content=extra.pop("content", f"Returns, version {version}."),
        source_id=extra.pop("source_id", "shop/returns"),
        version=version,
        effective_at=effective,
        expires_at=expires,
    )


OLD = passage("returns-v1", "1", "2025-06-01", "2026-03-01", content="Returns within 45 days.")
NEW = passage("returns", "2", "2026-03-01", content="Returns within 30 days.")
NEXT = passage("returns-v3", "3", "2027-01-01", content="Returns within 21 days.")
UNVERSIONED = Policy(policy_id="guide", title="Guide", content="How to pick a tent.")


def verdicts(policies: list[Policy]) -> dict[str, str]:
    return {p.policy_id: v for p, v in check_terms(policies, NOW).verdicts}


def test_the_version_in_force_passes_and_its_neighbours_drop_quietly():
    check = check_terms([OLD, NEW, NEXT, UNVERSIONED], NOW)
    assert check.current == [NEW, UNVERSIONED]
    assert verdicts([OLD, NEW, NEXT]) == {
        "returns-v1": SUPERSEDED,
        "returns": CURRENT,
        "returns-v3": SCHEDULED,
    }
    assert not check.withheld


def test_a_source_with_no_version_or_two_versions_in_force_is_withheld():
    lapsed = passage("promo", "1", "2025-11-01", "2026-02-01", source_id="shop/promo")
    early = passage("future", "1", "2027-01-01", source_id="shop/future")
    rival = passage("returns-v2b", "2b", "2026-06-01")
    check = check_terms([lapsed, early, NEW, rival, OLD], NOW)
    assert check.current == []
    assert verdicts([lapsed, early, NEW, rival, OLD]) == {
        "promo": EXPIRED,
        "future": NOT_IN_FORCE,
        "returns": CONFLICT,
        "returns-v2b": CONFLICT,
        "returns-v1": SUPERSEDED,
    }


def test_the_clock_decides_which_version_is_current():
    before = check_terms([OLD, NEW], datetime(2026, 1, 15, tzinfo=UTC))
    assert before.current == [OLD]
    # A naive policy date reads as UTC; a session clock in another zone compares cleanly.
    assert NEW.effective_at == datetime(2026, 3, 1, tzinfo=UTC)


def test_a_source_needs_its_version_and_effective_date():
    with pytest.raises(ValueError):
        Policy(policy_id="x", title="X", content="x", source_id="shop/x")


@pytest.fixture
def clocked(backend, config, skills, state, monkeypatch):
    def build(policies: list[Policy]) -> ShoppingToolExecutor:
        async def search(session, query):
            del session, query
            return policies

        monkeypatch.setattr(backend, "search_policies", search)
        return ShoppingToolExecutor(
            backend=backend,
            config=config,
            skills=skills,
            session=ShoppingSessionContext(session_id="s-1", user_id="u-1", now=NOW),
            state=state,
            memory=build_memory(config, InMemoryMemoryStore()),
        )

    return build


async def test_search_returns_the_current_version_with_its_evidence(clocked, state):
    result = await clocked([OLD, NEW]).execute("search_policies", {"query": "returns"})
    assert result.blocked is None
    assert "30 days" in result.result_text and "45 days" not in result.result_text
    assert '"source_id": "shop/returns"' in result.result_text
    assert '"version": "2"' in result.result_text
    assert result.evidence == [
        {
            "source_id": "shop/returns",
            "version": "1",
            "effective_at": "2025-06-01",
            "status": SUPERSEDED,
        },
        {
            "source_id": "shop/returns",
            "version": "2",
            "effective_at": "2026-03-01",
            "status": CURRENT,
        },
    ]
    assert list(state.seen_policies) == ["returns"]


async def test_a_conflict_is_held_by_the_terms_gate(clocked, state):
    rival = passage("returns-v2b", "2b", "2026-06-01", content="Returns within 60 days.")
    result = await clocked([NEW, rival]).execute("search_policies", {"query": "returns"})
    assert result.blocked == TERMS_GATE
    assert "versions 2 and 2b are both in force" in result.result_text
    assert "30 days" not in result.result_text and "60 days" not in result.result_text
    assert "support flow" in result.result_text
    assert state.seen_policies == {}


async def test_passages_in_force_still_answer_beside_a_withheld_source(clocked):
    lapsed = passage(
        "promo", "1", "2025-11-01", "2026-02-01", source_id="shop/promo", content="Promo terms."
    )
    result = await clocked([lapsed, NEW]).execute("search_policies", {"query": "returns"})
    assert result.blocked is None
    note, _, fenced = result.result_text.partition("\n")
    assert note.startswith("Withheld by the terms check: shop/promo (version 1 expired 2026-02-01)")
    assert "30 days" in fenced and "Promo terms" not in fenced


async def test_a_search_that_finds_nothing_says_so_in_a_flag(clocked):
    empty = await clocked([]).execute("search_policies", {"query": "warranty"})
    assert empty.no_match and empty.blocked is None and not empty.evidence
    found = await clocked([NEW]).execute("search_policies", {"query": "returns"})
    assert not found.no_match


async def test_a_guide_cites_the_passages_it_states(clocked, state):
    executor = clocked([NEW])
    await executor.execute("search_policies", {"query": "returns"})
    guide = {
        "title": "Returning an item",
        "sections": [{"heading": "Window", "body": "30 days from delivery."}],
        "policy_ids": ["returns"],
    }
    result = await executor.execute("present_guide", guide)
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    assert payload["evidence"] == [
        {
            "policy_id": "returns",
            "source_id": "shop/returns",
            "version": "2",
            "effective_at": "2026-03-01T00:00:00Z",
        }
    ]
    assert "policy_ids" not in payload

    unread = await executor.execute("present_guide", guide | {"policy_ids": ["returns-v1"]})
    assert unread.blocked == PROVENANCE_GATE
    assert "not returned by search_policies" in unread.result_text

    # A passage read while in force is refused once the clock passes its expiry.
    state.seen_policies["promo"] = passage("promo", "1", "2025-11-01", "2026-02-01")
    lapsed = await executor.execute("present_guide", guide | {"policy_ids": ["promo"]})
    assert lapsed.blocked == TERMS_GATE


async def test_a_disclosure_citing_lapsed_terms_is_refused(clocked, backend, state, monkeypatch):
    executor = clocked([NEW])
    await executor.execute("search_products", {"query": "tent"})
    lapsed = OLD.evidence()

    async def disclosure(session, product_id):
        del session
        return Disclosure(
            title="Facts",
            product_id=product_id,
            rows=[DisclosureRow(label="Returns", value="45 days")],
            evidence=[lapsed],
        )

    monkeypatch.setattr(backend, "get_disclosure", disclosure)
    executor._config = executor._config.model_copy(update={"enable_disclosures": True})
    result = await executor.execute("present_disclosure", {"product_id": "p-100"})
    assert result.blocked == TERMS_GATE
    assert "shop/returns v1" in result.result_text
