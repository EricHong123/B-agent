# scheduled-digest

`run_morning_digest.py` runs the digest without an operator: one `MerchantAgent` turn
(`merchant_agent_runtime`, the Messages API runtime) over the retail example's mock
merchant, asking what needs attention today. It prints the reply and the `present_digest`
payload; `--out FILE` also writes the whole result (prompt, text, digest, other
components) as JSON. The environment variables `MERCHANT_ID` (default `acme-retail`),
`MERCHANT_OPERATOR` (default `scheduled-digest`), and `MERCHANT_TIMEZONE` (unset: the
machine's local date is today) set the session it runs as; `build_demo_agent` is the function
to replace with a `MerchantAgent` over your own `MerchantBackend`.

```bash
python merchant-agent/managed-agents/scheduled-digest/run_morning_digest.py --out digest.json
```

Credentials: the runtime's default client reads `ANTHROPIC_API_KEY` or
`ANTHROPIC_AUTH_TOKEN`. Exit status 2 means no credential worked, 1 any other failure.

- Run it from any job runner on the store's morning schedule, with the credential
  supplied from the runner's secret store.
- Keep the `--out` file as the job's artifact and let the exit status drive retries. The
  config it builds keeps `require_host_approval` on and the session starts with nothing
  approved, so a repeat run can stage a change but never apply one.
- Deliver the `digest` field to systems and the text to people; an item whose `ref_id` a
  tool returned during the turn carries that listing or change record (`enrich_digest`).

Tests: `merchant-agent/runtime-messages-api/tests/test_scheduled_digest.py` runs
`run_digest` against `commerce_common.testing.FakeClient`.
