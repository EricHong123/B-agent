# commerce-builder (Claude Code plugin)

Six skills, four commands, and two hooks for building a shopping agent or a merchant agent on the
packages in this repo ([`../../README.md`](../../README.md)), or bringing one that exists onto
them. Skills and commands alike load when a conversation matches their description, and a command
can also be typed; the commands read the reference repo (this checkout, a local clone, or a fresh
one) while they run. The hooks are the plugin's only code: two Python scripts with no
dependencies beyond `python3`.

## Install

```bash
claude plugin marketplace add anthropics/commerce-agents     # or the path of a local clone
claude plugin install commerce-builder@claude-commerce-agents
```

## Commands

| Command | Does |
|---|---|
| [`/scaffold-commerce-agent`](commands/scaffold-commerce-agent.md) | Interviews you about your stack, plays the plan back, and scaffolds a shopping agent, a merchant agent, or both on the reference packages |
| [`/add-commerce-flow <flow>`](commands/add-commerce-flow.md) | Adds one shopping or merchant flow to an existing agent: copies its skill, wires the tools it calls, authors its first eval cases |
| [`/author-commerce-evals`](commands/author-commerce-evals.md) | Builds the eval suite: a runner, the first ten cases against your own catalog, and a replay gate for CI |
| [`/review-commerce-agent`](commands/review-commerce-agent.md) | Maps an agent you already run, compares it with the reference row by row, and converts the rows you pick |

The scaffold and the review write what they learned to your project's `CLAUDE.md` under
`## Commerce agent decision record`; the other two commands read that section instead of asking again.

## Hooks

| Hook | Runs | Does |
|---|---|---|
| [`secret_guard.py`](hooks/secret_guard.py) | before Write and Edit | Refuses text that hardcodes a live credential (a model API key, a live payment key, a cloud access key, a private key) in any file but a local `.env`; the message tells Claude to read it from the environment |
| [`prompt_bytes.py`](hooks/prompt_bytes.py) | after Write and Edit | After an edit to `prompt.py`, `fencing.py`, `tools/registry.py`, a skill's `SKILL.md`, or `agent.yaml`, reminds Claude to keep those bytes stable across requests, re-derive the Managed Agents `system.md`, and re-record the eval replay; blocks nothing |

`COMMERCE_BUILDER_HOOKS=0` turns both off. [`hooks/hooks.json`](hooks/hooks.json) declares them,
and `scripts/check.py` checks that every script it names exists.

## Skills

| Skill | Rules for |
|---|---|
| [`commerce-architecture`](skills/commerce-architecture/) | One model per conversation, the backend interface, and which layer (tool description, prompt, skill) a rule belongs in |
| [`commerce-prompt-caching`](skills/commerce-prompt-caching/) | Keeping the static prompt and tool list byte-stable, and checking that requests hit the cache |
| [`commerce-ui-tools`](skills/commerce-ui-tools/) | Presentation tools, server-side enrichment, the event stream, and adding a component |
| [`commerce-trust-safety`](skills/commerce-trust-safety/) | Fencing, provenance and caps, identity, gate state, grounding, memory writes, adversarial cases |
| [`commerce-evals`](skills/commerce-evals/) | The case shape, the scorers, hostile fixtures, and the run pattern |
| [`commerce-merchant-operations`](skills/commerce-merchant-operations/) | Staged changes, guardrails, host approval, metrics grounding, and marketplace scoping |

## Path

1. `/scaffold-commerce-agent`, then wire the backend methods it stubbed; with an agent already
   running, `/review-commerce-agent` and the rows it converts.
2. `/add-commerce-flow` for each flow in your v1 index.
3. `/author-commerce-evals`, and re-record after every prompt, skill, or runtime change.
4. Deploy per [`../../docs/deployment.md`](../../docs/deployment.md).

Authentication, and the memory controls a deployment owes its users, are wired by the deployment;
[`../../docs/safety.md`](../../docs/safety.md) lists them. Where this plugin's text and the
reference code disagree, the code is right.
