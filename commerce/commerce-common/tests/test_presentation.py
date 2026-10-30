# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest
from pydantic import BaseModel, ValidationError

from commerce_common.presentation import (
    EnrichmentContext,
    PresentationComponent,
    PresentationExtension,
    PresentationRefused,
    PresentSuggestionsPayload,
    enrich_partial,
    partial_signature,
    run_presentation,
)


class _Payload(BaseModel):
    ident: str
    suggestions: list[str] = []


def _context() -> EnrichmentContext:
    return EnrichmentContext(backend=None, config=None, session=None, state={"known": 1})


def test_suggestions_payload_sanitizes_and_rejects_a_list_that_sanitizes_away():
    payload = PresentSuggestionsPayload.model_validate(
        {"suggestions": ["y" * 200, "Add\u200b to\x07cart", "\u200b\ufeff", "Compare the top two"]}
    )
    assert payload.suggestions == ["y" * 79 + "…", "Add to cart", "Compare the top two"]
    with pytest.raises(ValidationError):
        PresentSuggestionsPayload.model_validate({"suggestions": ["a", "b", "c", "d", "e"]})
    with pytest.raises(ValidationError, match="empty after sanitization"):
        PresentSuggestionsPayload.model_validate({"suggestions": ["\u200b\ufeff", "\x00\x01 "]})


async def test_component_without_a_hook_renders_the_payload_as_sent():
    spec = PresentationComponent(name="present_x", component="x", payload_model=_Payload)
    outcome = await run_presentation(spec, {"ident": "a"}, _context(), "Displayed.")
    assert outcome.result_text == "Displayed."
    (event,) = outcome.events
    assert event.type == "ui" and event.data == {
        "component": "x",
        "payload": {"ident": "a", "suggestions": []},
    }


async def test_invalid_payload_is_an_error_naming_the_tool():
    spec = PresentationComponent(name="present_x", component="x", payload_model=_Payload)
    outcome = await run_presentation(spec, {}, _context(), "Displayed.")
    assert outcome.is_error and outcome.result_text.startswith("Invalid present_x payload:")
    assert outcome.events == []


async def test_hook_notes_join_the_result_text_and_the_payload_renders_as_enriched():
    async def enrich(payload: _Payload, context: EnrichmentContext) -> dict:
        context.notes.append("Skipped b.")
        return {"ident": payload.ident, "rows": [1, 2]}

    spec = PresentationExtension(
        name="present_x",
        component="x",
        payload_model=_Payload,
        enrich=enrich,
        description="d",
        input_schema={"type": "object"},
    )
    outcome = await run_presentation(spec, {"ident": "a"}, _context(), "Displayed.")
    assert outcome.result_text == "Displayed. Skipped b."
    assert outcome.events[0].data == {"component": "x", "payload": {"ident": "a", "rows": [1, 2]}}


@pytest.mark.parametrize(
    ("raised", "is_error", "blocked"),
    [
        (PresentationRefused("no ids", "provenance"), False, "provenance"),
        (PresentationRefused("no record"), True, None),
        (ValueError("hook says no"), True, None),
    ],
)
async def test_hook_refusals_map_onto_held_or_error(raised, is_error, blocked):
    async def enrich(payload: _Payload, context: EnrichmentContext) -> dict:
        raise raised

    spec = PresentationComponent(
        name="present_x", component="x", payload_model=_Payload, enrich=enrich
    )
    outcome = await run_presentation(spec, {"ident": "a"}, _context(), "Displayed.")
    assert outcome.result_text == str(raised)
    assert (outcome.is_error, outcome.blocked) == (is_error, blocked)
    assert outcome.events == []


def test_partial_signature_tracks_titles_and_list_growth():
    empty = partial_signature({"items": []})
    one = partial_signature({"items": [{"product": {}}]})
    titled = partial_signature({"title": "T", "items": [{"product": {}}]})
    assert empty != one != titled
    steps = partial_signature({"steps": [{"products": []}]})
    steps_filled = partial_signature({"steps": [{"products": [{}]}]})
    assert steps != steps_filled
    assert partial_signature({"days": [{"products": [{}]}]}) == partial_signature(
        {"days": [{"label": "other", "products": [{}]}]}
    )


def test_a_partial_with_no_title_and_only_empty_lists_is_not_a_frame_yet():
    def passthrough(data, state):
        del state
        return dict(data)

    spec = PresentationComponent(
        name="present_rows", component="rows", payload_model=_Payload, enrich_partial=passthrough
    )
    assert enrich_partial(spec, {"items": []}, None) is None
    assert enrich_partial(spec, {"title": "T", "items": []}, None) == (
        "rows",
        {"title": "T", "items": []},
        (True, {"items": 0}),
    )
    assert enrich_partial(spec, {"items": [{}]}, None)[2] == (False, {"items": 1})
    # A payload with no lists at all (a preview keyed by id) is a frame on its own.
    assert enrich_partial(spec, {"change_id": "chg-1"}, None) is not None
    without_hook = PresentationComponent(name="x", component="x", payload_model=_Payload)
    assert enrich_partial(without_hook, {"title": "T"}, None) is None
