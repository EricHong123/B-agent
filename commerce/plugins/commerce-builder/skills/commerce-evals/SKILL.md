---
name: commerce-evals
description: Authoring and running behavioral evals for a shopping or merchant agent, covering the case shape, authoring rules, code graders and judges, the run pattern, and poisoned fixtures. Load when writing eval cases or rubrics or deciding how a suite runs.
---

# Commerce agent evals

The repo ships no eval harness; the suite is yours, because a case only means something against your catalog,
orders, and fixtures. Paths below are in the reference repo: `commerce_common/` is `commerce-common/commerce_common/`.
Gate behavior that needs no model (provenance, caps, guardrails, approval) is unit-tested with `FakeClient` in
`commerce_common/testing.py`; evals cover what the model decides.

## The case shape

This block is the one home of the case shape and the scorer names; `/author-commerce-evals` refers to it.

```json
{
  "id": "<flow>-<nnn>-<behavior>",
  "priority": "critical | high | medium | low",   "difficulty": "easy | medium | hard",   "tags": ["..."],
  "skip": "<reason, when a case cannot run yet>",
  "state": {"seen_products": ["..."], "cart": [...], "memory": [...], "staged_changes": [...]},
  "turns": ["<the customer's or operator's message>", "..."],
  "expected": {
    "calls_tool": ["..."],            "calls_one_of": ["..."],          "never_calls": ["..."],
    "first_tool": "...",              "first_tool_not": "...",
    "ui_components": ["..."],         "no_ui": true,
    "cart_contains": ["..."],         "cart_item_count": 0,             "cart_not_contains": ["..."],
    "staged_change_kinds": ["..."],   "no_applied_changes": true,
    "memory_contains": ["..."],       "memory_not_contains": ["..."],
    "skill_loaded": "...",            "skill_not_loaded": "...",        "no_skill_load": true,
    "reply_includes": ["..."],        "reply_omits": ["..."],           "max_tool_calls": 0,
    "rubric": "PASS if <condition>. FAIL if <condition>."
  },
  "notes": "<what the case pins and the fixture fact that decides it>"
}
```

`state` is the precondition; `turns` is one message unless the behavior under test is carrying state across turns;
`expected` holds only the keys the case is about. Ids in `state` and `expected` are real ids from your fixtures.
`priority` and `difficulty` let a report say which failures matter; a case that cannot run yet carries `skip`
with its reason rather than being deleted.

## Authoring rules

- Preconditions go in injected state (the products already seen, the cart, the memory facts, the staged queue), which
  the runner loads into the session state and the memory store before the turn. Earlier turns are for state the
  behavior itself carries, and for nothing else.
- Every positive has a negative: for each case that asserts a component, a skill load, a gate, a disclosure, or a
  memory write, a case in the same niche asserts its absence. A refusal case has a should-serve counterpart.
- Memory is three cases: a remark worth keeping is written; an identifier or excluded content is refused (nothing
  stored, no error to the person); a stored fact changes the next session's pick.
- Grade the final tool arguments and the state they produced: the ids on the last presentation call, the fields on
  the staged change, the cart and the memory store after the turn. The reply's wording is graded only for strings
  that must or must not appear. Which route the agent took (`skill_loaded`, one named component, `never_calls` on a
  presentation tool) is asserted only where the route is the behavior (a grounding read first, a write that must
  never happen); elsewhere `calls_one_of` names the acceptable set. When a live run takes a route the case did not
  expect and the answer was right, widen the case to the acceptable set; do not re-pin it to the route observed.
- A rubric is one PASS condition and one FAIL condition that no response satisfies both of; it names the fixture
  fact that decides it (the updated delivery date, the price today); variants you accept are written into it; it
  says nothing about tone, length, or the order components appear in.
- A turn that mentions health, a one-off errand, or hostile content asserts the memory end-state
  (`memory_not_contains`, or `never_calls` on `save_memory`). A case where a stored fact should change the pick uses a
  query whose results contain both the item the fact favors and the one it rules out; run the search before writing
  the case.
- `max_tool_calls` is set from what a well-behaved agent needs; a multi-item request fans out several searches in one round, and the `present_suggestions` call that ends the turn is not counted.

## Scorers

- Code graders read the events a turn yields (`commerce_common/streaming.py`): `tool_call` names and arguments,
  `tool_result` with `status` `blocked` and the gate in `reason`, `ui` component names, the last `cart_update` or
  `change_update`, and the reply text. Every key above except `rubric` is a code grader.
- `rubric` goes to a judge. One judge call per dimension (budget respected, no invented availability, trade-off stated),
  returning structured output with a verdict and a reason; the transcript is passed to it as quoted material, tool
  results and component payloads included; when the transcript exceeds the judge's window, truncate from the start so
  the graded turn survives, and record the truncation on the outcome. Pin the judge model at temperature zero; a change to the judge model or a rubric
  invalidates every stored verdict scored with it, so the recording carries a fingerprint of both.
- A judge reply that does not parse into a verdict is a judge failure on the case, kept apart from an agent failure.

## Run pattern

| When | What runs | What decides |
|---|---|---|
| Every merge to the agent, a skill, a tool description, or a fixture | The regression set | Each case over several trials; a pass threshold per set |
| While changing one flow | That flow's targeted set | The failure set, read beside the previous run's as the baseline |
| Choosing or upgrading a model (commerce-architecture's model fields) | Everything | The two failure sets side by side |
| In production | A judged sample of live traffic against the same rubrics | Trend per dimension |

Diff failure sets; a topline moving a point between live runs is noise. A case that fails after a change means the
change broke the behavior or the case encoded a stale one; fix whichever it is and say which in the commit.

## Poisoned fixtures

Listings, reviews, and messages carrying instructions live in eval-only fixtures the runner merges into the backend
for the run, under a third-party brand or seller; none of their ids appears in demo data, seeds, or captures. Each
such case asserts the negative in code (`never_calls`, `cart_not_contains`, `no_applied_changes`,
`memory_not_contains`, `reply_omits`), and every vector it asserts is one the driven turn actually puts in front of
the model (a review is only read on a details call). Cover at least an instruction to write to the cart or stage a
change, one to remember something, and a false claim (a code, a guarantee). The should-serve counterpart is a
separate benign eval-only listing in the same niche, so an agent that refuses everything fails it.
