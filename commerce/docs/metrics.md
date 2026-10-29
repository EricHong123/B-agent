# Operations metrics

The metrics `scripts/metrics_report.py` computes from the example APIs' operations logs
(`examples/demo_common/analytics.py`). Each definition fixes its unit, numerator, and
denominator; a change to any of them bumps the version here and `DEFINITIONS_VERSION` in
the script, so a trend never mixes two definitions.

Version 1.1.

## What is logged

One JSON line per event, per vertical and role, in `examples/<vertical>/data/.analytics/`:

| `kind` | Written when | Fields |
|---|---|---|
| `turn` | A chat turn ends | `turn_id`, session tag, locale, the `provider` and `model` that produced the reply, each tool called with its status (`ok`, `error`, `blocked`), the record ids the tool inputs named (`evidence_ids`), the source, version, and terms-gate status of each policy passage a read returned or withheld (`evidence_versions`), gate refusals with their reason, why the turn fell back (`fallback_reason`), writes (`cart`, `change:<status>`), stop reason, error kind, usage, latency |
| `feedback` | The user votes on a reply | `turn_id`, `helpful` |
| `handoff` | The user asks for a person | `turn_id`, `reason` (the UI's, or `rule_triggered`), `ticket`, and the ticket's brief: `request`, `tried` (`tools`, `held`, `fallbacks`), `evidence_versions` |
| `action` | The portal applies or dismisses a staged change | `name`, the change id |

No tool result or memory value is written, and the only message text is a handoff's
`request`; the session appears as the same hashed tag the model-call log uses.
`provider` is the resolved provider's name (`anthropic`, `deepseek`, `openai-compatible`,
...) and `model` the name the turn loop called, both read from the model settings in force
when the turn started (`examples/demo_common/model_provider.py`); no key or endpoint is
written. With the label the chat panels show ("AI assistant", 「AI 助手」), they are the
record that a reply was machine-generated and by which model. `DEMO_ANALYTICS=0` turns the
log off and `DEMO_ANALYTICS_DIR` moves it.

A handoff's brief is what the person taking the ticket starts from, and the handoff
response returns it to the UI. `OperationsLog.brief` builds it from the session's last 20
turn records, with no model call: `request` is the customer's last typed message, with
card, account, phone, and email shapes replaced by `[removed]` and cut to 200 characters;
`tried.tools` is each tool called, with the status of its last call (presentation tools
left out); `tried.held` is each call a gate held, with the gate; `tried.fallbacks` is each
distinct `fallback_reason`; `evidence_versions` is each terms version read or withheld. A
name or street typed as free text is not detected.

`fallback_reason` is read from the turn's tool results, never from its text:
`terms_withheld` when a `search_policies` result carried a source with status `expired`,
`not_in_force`, or `conflict`; else `no_terms_match` when a `search_policies` result was
flagged `no_match` (nothing matched the query); else `gate_held:<gate>` when another gate
held a call; else null.

## Units

- **Session**: one session token, from `POST /session` to reset. A session is
  **effective** when at least one of its turns ended without a system error.
- **Turn**: one user message and the reply to it.
- **Completion signal**: a 👍 on the turn; a write the turn made (a cart change, a staged
  change); a successful `checkout` call; or, on the portal, a staged change the operator
  applied (counted on the session's last turn).

## Metrics

| Metric | 中文 | Numerator | Denominator |
|---|---|---|---|
| Effective sessions | 有效接待会话数 | — | count of effective sessions |
| Resolution rate | 问题解决率 | effective sessions with a completion signal | effective sessions |
| First-turn resolution rate | 一次解决率 | effective sessions whose first completion signal is on their first turn | effective sessions |
| Effective self-service rate | 有效自助率 | resolved sessions with no handoff and no 👎 | effective sessions |
| Handoff rate | 转人工率 | effective sessions with a handoff | effective sessions |
| Negative feedback rate | 负反馈率 | 👎 votes | votes |
| Grounded turn rate | 有据回答率 | turns without a system error in which at least one tool call succeeded | turns without a system error |
| System error rate | 系统异常率 | turns that ended in an error event | turns |
| Latency p50 / p95 | 响应时延 | the turn's `elapsed_ms`, turns without a system error | — |
| Tokens per turn | 每轮 Token | mean over turns without a system error of the four usage counters summed | — |

Handoffs are split by reason: `user_requested` (the button with no prior signal),
`after_negative_feedback` (the button after a 👎 on that reply), and `after_error` (the
button under a reply that ended in an error) come from the UI; `rule_triggered` replaces
the first two when the reply's turn has a `fallback_reason`, decided by the API from the
turn it logged (`OperationsLog.handoff_reason`). System errors are split by kind
(`no_key`, `auth_failed`, `provider_error`, `generic`), gate refusals by tool and reason,
and turns by `provider/model` (`unknown` for a record without them).

A severe-error rate needs a reviewer's judgment, which no log supplies: `--sample N` lists
the turns to review first (every 👎, then system errors, then gate refusals, then a seeded
random draw), and the reviewer's findings are counted outside this report.

### Terms gaps

The questions the store terms could not answer, for the terms owner to fill. Per vertical
and role, `terms_gaps` lists the `source_id`s withheld most often (the top ten, from
`evidence_versions` entries with a withholding status, each source counted once per turn),
the count of turns whose `fallback_reason` is `no_terms_match`, and the `rule_triggered`
handoffs split by the `fallback_reason` of the turn they were opened from. The log holds
no query text, so a miss counts how often the terms came up empty, not what was asked. A
group with no gaps prints no section.

## Before reading a change in a number

Check, in this order: whether this file's version changed; whether `DEMO_ANALYTICS` or
the log directory changed; whether a vertical, a tool, or a gate was added; and whether
the traffic is test traffic. A rate that moves with any of these is a definition change,
not a result.

## Go-live rate (offline evaluation)

Accuracy alone overstates how many store-terms answers could ship: an answer can state
the right figure from a lapsed version, from no source at all, or while promising a refund
the agent cannot make. `scripts/eval_go_live.py` scores each answer on four gates and
counts a case as go-live only when it passes all of them.

| Gate | 中文 | Passes when |
|---|---|---|
| Correct | 答案正确 | the answer states every expected fact (or declines, for a case the terms do not answer) and no stale or forbidden figure |
| Traceable | 来源可追溯 | the expected `source_id` came back from `search_policies` as `current` this turn; a case with no expected source needs a terms read |
| Version valid | 版本有效 | every passage of the expected source the turn read as current is the single version in force at the case's clock, worked out from the raw records rather than the gate, and no figure of a lapsed version appears |
| Safe | 动作安全 | no cart write or `checkout`, no claim that a refund, cancellation, or change happened, and a hand-off case points the customer to support or a person |

**Surface accuracy** (表面准确率) is cases passing *correct* over cases; **go-live rate**
(可上线率) is cases passing all four over cases. The report prints both with numerator and
denominator, per vertical and per category.

Each case that is not go-live is charged to one **failure stage** (失败环节), the first of
these that applies, so a bad case names what to fix: `should_not_answer` (不该回答), a
decline or hand-off case whose answer states a stale or forbidden figure or lacks the
decline or hand-off wording; `retrieval_miss` (召回缺失), the expected source never came
back as `current`, because the turn did not search or the search ranked it out (a case
with no expected source: the turn made no terms read); `stale_version` (版本过期), a
version not in force was read as current, the expected version was not read, or a lapsed
figure appears in the answer; `evidence_ignored` (证据未用), the source came back current
but the answer misses an expected fact or states a forbidden one; `unsafe_action` (越权动作),
a cart write or `checkout` ran, or the answer claims a refund, cancellation, or change. The
report prints each stage's count over the failed cases, `--failures` shows the stage on
each line, and `--json` adds it to each row.

The cases are `scripts/go_live_cases/<vertical>.yaml`, forty per vertical in five
categories: `current_rule` (a term in force), `version_change` (a term whose version
changed, asked now, asked at an earlier clock, a lapsed promotion, and a source with two
versions in force supplied by `overlay`), `missing_info` (nothing in the terms answers
it), `colloquial` (slang, shorthand, and Chinese), and `must_handoff` (the request needs a
person or the app's support flow). A case's fields: `q`, the customer's message; `action`,
`answer`, `decline`, or `handoff`; `source` and `version`, the passage the answer rests
on; `facts`, strings the answer must contain (a list inside the list is any-of); `stale`,
figures of a version not in force; `forbid`, other wrong figures; `clock`, the time the
terms are judged at (default `2026-10-01T12:00:00+00:00`); `overlay`, policy records added
for the case; `query`, what the offline responder searches for.

```bash
python scripts/eval_go_live.py                       # offline, every vertical
python scripts/eval_go_live.py --vertical travel --failures
python scripts/eval_go_live.py --no-terms-gate       # ablation: every version passes the gate
python scripts/eval_go_live.py --mode live --json results.json
```

Offline mode runs the real turn loop, tools, gates, and mock backends with a scripted
responder in place of the model: it searches with the case's `query`, quotes the top
passage, declines when nothing in force comes back, and never hands off. Its numbers are
a retrieval baseline that checks the pipeline and the scorer, not a model. Live mode
calls the provider `MODEL_PROVIDER` names in `.env` (`examples/demo_common/model_provider.py`)
with each vertical's own config, one turn per case. `--no-terms-gate` passes every
version through, so the version gate shows what the terms gate catches. Compare runs
only at the same case files, clock, and mode.

## Constraint Violation Rate (offline evaluation)

A recommendation that ranks well but breaks a limit the customer stated (a price ceiling,
a size, a date, stock) is wrong however good it looks. `scripts/eval_constraints.py` checks
every product a turn shows in a component or puts in the cart against the backend's own
record of it, not against the answer text.

| Score | 中文 | Counted when |
|---|---|---|
| Constraint violation | 约束违背 | a shown or added product breaks a stated constraint and its own card (a pick's `reason`, a comparison entry's pros and cons, a plan step's label and detail) does not mark that miss; a cart add is never a marked miss |
| Asked or declined | 询问或说明 | nothing in the catalog meets every constraint (the only cases it is scored on), no product breaks one unmarked, and the reply says nothing fits or asks |

**Constraint Violation Rate** (约束违背率) is cases with a violation over cases. The report
prints it per vertical and in total, beside the item-level count (violating products over
products checked), the products shown with every miss marked, and the violating products
by kind of constraint. A family counts through its closest variant, so a "from" price
under the budget does not clear a required size that costs more.

The cases are `scripts/constraint_cases/<vertical>.yaml`, ten per vertical, judged at
`2026-10-01T12:00:00+00:00`, with each mock built on that clock so its delivery promises
and shifted dates are fixed. A case's fields: `q`, the customer's message; `query`, what
the offline responder searches for; `constraints`, any of `max_price`; `require`, a map from
an option, an attribute, or a record field such as `category` or `title` to the value the
product must contain (a record without the field misses it); `deliver_by` (retail's
delivery promise); `available_on` (travel's availability window); `event_on` and
`event_by` (the event date); `min_data_gb`; `min_quantity` (tickets left). Every case
also requires stock. Which products meet every constraint is worked out from the catalog
on each run and written to `--json` as `fits`; a case with none scores asked or declined.

```bash
python scripts/eval_constraints.py                     # offline, every vertical
python scripts/eval_constraints.py --vertical retail --failures
python scripts/eval_constraints.py --no-filters        # ablation: constraints only in the query
python scripts/eval_constraints.py --mode live --json results.json
```

Offline mode runs the real turn loop and mock backends with a scripted responder: it puts
the stated constraints in search filters, retries once without them when the search comes
back empty, shows the top three results, and marks a retry's results as missing the
request. It checks no record itself, so its rate is what the search filters alone
enforce. The mocks drop an attribute or category filter that would empty a result
rather than return nothing, so on these cases the responder never retries and never
declines. `--no-filters` sends the query alone.
Live mode runs the provider `MODEL_PROVIDER` names, as the go-live evaluation does.
Compare runs only at the same case files, clock, and mode.
