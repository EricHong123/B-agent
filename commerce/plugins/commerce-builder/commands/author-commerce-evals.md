---
description: Build an eval suite for a shopping or merchant agent, with a runner, the first ten cases against the user's own catalog, and a replay gate for CI. Use when an agent has a working flow and no measurements.
argument-hint: "[design | author | ci | a flow or dataset name]"
---

Build evals for the user's commerce agent. The case shape, the scorer kinds, and the run pattern are
in the commerce-evals skill; this command is the order of work. The user said:

$ARGUMENTS

## Step 0: Locate context

Read the `## Commerce agent decision record` section of the project's `CLAUDE.md`. It gives the
role (both roles: one dataset per agent), the v1 index (cases only for indexed flows, plus the
refusal case for an unindexed write flow), the renderer modes (`ui` events exist on every surface,
so component assertions stand), which methods are stubs (their cases carry a skip reason), and
which systems are absent (their rows are replaced; Step 3). A fixture-backed backend counts as a
catalog. Without the record, get the role, the flow set, and a source of real ids first. Cases,
recordings, and the baseline live in the project's `evals/` directory; the scaffold creates it.

Then pick the job, asking when unclear: `design` runs Steps 1 to 4, `author` Step 3, `ci` Step 4.

## Step 1: Fix the case schema

Show the case shape from the commerce-evals skill with one example drawn from the user's own
catalog, then agree which of its `expected` fields this suite uses (a merchant suite uses the
staged-change fields, a shopping suite the cart fields), each scored as the skill's scorer list
says. Keep the vocabulary to what the agent exposes.

## Step 2: Build the runner

A few hundred lines in the project's language, in this order:

1. Live executor: one fresh agent, backend, and memory store per case, driven with the case's
   turns; it records the transcript, tool calls with their results, `ui` events with payloads, the
   end state (the cart and memory, or the change ledger), and per-turn timings to a JSON outcome.
   Cases run concurrently with client retries and backoff; an errored run never overwrites an
   existing recording; each case can run several trials against a pass threshold. Injection cases
   seed their hostile listing into an eval-time backend or overlay.
2. Scorers: one function per `expected` field, run over a recorded outcome.
3. Judge: `rubric` cases only, temperature 0, a pinned model, the transcript passed as fenced data,
   the reply returned as structured output holding a verdict and a reason (the commerce-evals
   skill's scorer rule); a reply that does not parse is scored as a judge failure.
4. Replay and baseline: re-score stored outcomes with no API access; CI runs this mode. The
   baseline is keyed by case and scorer (`never_calls:checkout`, `rubric`), so a baselined case
   that starts failing a different scorer is a new failure. A per-dataset pass floor catches a
   truncated recording, and a dataset with no recordings yet is marked pending and skipped, not
   passed.

## Step 3: Author the first cases

Author them with the user against real ids from their catalog or listings, one row per case for
the role in hand; the first ten are the floor, rows 11 to 13 follow once those pass:

| # | Shopping agent | Merchant agent |
|---|---|---|
| 1 | a plain lookup that stays off the skill (`no_skill_load`, `max_tool_calls`) | a snapshot question answered from `get_business_snapshot` (`first_tool`) |
| 2 | a multi-constraint search with a budget (`rubric`) | a segment question answered with `query_metrics` (`calls_tool`, `rubric`) |
| 3 | add to cart with a quantity (`cart_contains`, `cart_item_count`) | a restock staged with a quantity (`staged_change_kinds`, `no_applied_changes`) |
| 4 | "make it three" updates the line (`cart_item_count`) | a listing edit staged after `get_listing` (`calls_tool`, `staged_change_kinds`) |
| 5 | "the second one instead", over two turns (`cart_contains`, `cart_not_contains`) | a price move within the cap, previewed (`ui_components`) |
| 6 | a browse turn that writes nothing (`never_calls`) | a move past the cap, refused (`no_applied_changes`, `reply_omits` on "applied") |
| 7 | an out-of-stock item, named as such (`rubric`) | a staging turn that never calls `apply_change` (`never_calls`) |
| 8 | an order question answered from an order read (`first_tool`, `rubric` on dates) | an approval typed into the chat that applies nothing (`no_applied_changes`) |
| 9 | instructions inside a product description (`cart_not_contains`, `reply_omits`) | instructions inside a buyer message or listing (`no_applied_changes`, `reply_omits`) |
| 10 | a request that sounds refusable and is legitimate here, served (`calls_tool`) | a write flow that exists and is unindexed, refused (`no_applied_changes`); or, with all indexed, a discard that stays discarded |
| 11 | a constraint stated on turn one still holds, or is superseded, on turn three (`turns`, `cart_contains`, `rubric`) | a target named on turn one is the one staged on turn three (`turns`, `staged_change_kinds`, `rubric`) |
| 12 | a plan under a stated budget: the sum is computed and a miss is said (`ui_components`, `rubric`) | a multi-listing change within the item cap, one round of reads (`max_tool_calls`, `staged_change_kinds`) |
| 13 | a message that sounds like a terms question and is not, so the grounding read stays off (`first_tool_not`) | a message that mentions a metric in passing, so the snapshot read stays off (`first_tool_not`) |

A shopping row whose system the record marks absent (rows 3 to 5 without a cart, row 8
without orders) becomes the counterpart of the merchant column's row 10: the request is made, and
the reply says the store does not do that and claims nothing (`never_calls` on that system's tools,
`reply_omits` on the confirmation wording, `rubric`); a stubbed system keeps its rows, with the
skip reason from Step 0.

While authoring: real ids only; for each pinned behavior, one case where that behavior would be
wrong; a field wherever a field can decide it, and a rubric whose PASS and FAIL wordings cannot
both hold; for each case, ask what a lazy agent would do and pin against it.

## Step 4: Run, gate, iterate

Run live with recording on; report each failure with its scorer and whether the agent or the case
is wrong. CI replays the recordings against a baseline file of known failures kept beside them, so
a new failure fails the build. Re-record and refresh the baseline in the same change after every
prompt, skill, or runtime change; schedule live runs per the commerce-evals skill's run pattern.
