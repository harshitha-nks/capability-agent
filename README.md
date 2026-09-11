# Capability Agent

Discover a UI flow with an LLM, save it as a typed "capability" artifact, and
replay it deterministically - no model in the loop at replay time. Built
against [saucedemo.com](https://www.saucedemo.com), a free public demo store
whose login → cart → checkout flow stands in for a "real" line-of-business
app's search → detail → action flow.

See `/REPORT.md` for the design write-up (architecture, schema rationale,
error handling, multi-tenant story, escalation model, safety, and cuts).

## 1. Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium   # downloads a browser binary, needs real internet
echo "ANTHROPIC_API_KEY=your-key-here" > .env   # then edit .env and paste in your real key
```

You need your own Anthropic API key (`ANTHROPIC_API_KEY` in `.env`). The
discovery run makes one Claude call per step; a full checkout-overview flow
is ~6-10 calls.

## 2. Run the browser-free logic tests (no key, no browser needed)

```bash
python3 -m tests.test_logic
```

This checks the artifact schema round-trips correctly, the guardrail policy
enforces domain/action allowlists and risky-action detection, and
`{{param}}` substitution works. It does **not** exercise the browser or the
LLM — see step 3 for the real end-to-end run.

## 3. Demo path: discover, then replay

**Discover** (real LLM-driven run against the live site; run headed so you
can watch, and so you're available if it asks for help):

```bash
python cli.py discover \
  --goal "Log in, add the Sauce Labs Backpack to the cart, and reach the checkout overview page" \
  --start-url "https://www.saucedemo.com" \
  --params '{"username":"standard_user","password":"secret_sauce","item_name":"Sauce Labs Backpack"}' \
  --secret-params username,password \
  --out artifacts/add_to_cart_and_checkout.json \
  --headed
```

This writes the artifact to `artifacts/add_to_cart_and_checkout.json` and a
full structured log + screenshots to `evidence/discover_<id>/`.

**Replay** (deterministic, no LLM, headless by default):

```bash
python cli.py replay \
  --artifact artifacts/add_to_cart_and_checkout.json \
  --params '{"username":"standard_user","password":"secret_sauce","item_name":"Sauce Labs Backpack"}'
```

Prints a structured JSON result (`success` / `business_outcome` / `failure`)
and writes logs + screenshots to `evidence/replay_<id>/`.

**Replay with a business outcome instead of a crash** — saucedemo's `locked_out_user`
is rejected at login with a visible error banner. This should NOT be treated
as a system crash — it's an expected, informative business outcome the
artifact was taught to recognize:

```bash
python cli.py replay \
  --artifact artifacts/add_to_cart_and_checkout.json \
  --params '{"username":"locked_out_user","password":"secret_sauce","item_name":"Sauce Labs Backpack"}'
```

Discovery now flags states like this automatically (see `agent/llm.py`'s
`outcome` action) — if the LLM notices an error/rejection state while
working toward the goal, it records it into the artifact's
`known_outcomes` on its own. An artifact recorded before this was added
(or one that never happened to encounter such a state during discovery)
won't have it — you can add a `known_outcomes` entry to the artifact JSON
by hand at any time; see `REPORT.md` section 3 for the schema shape.

## 4. Capability catalog (agent-facing invocation)

Every saved artifact can be listed and invoked by name, the way a production
AI agent would — no need to know it's a browser flow underneath:

```bash
python cli.py catalog                     # list saved capabilities as tool definitions
python cli.py invoke --capability cap_28b40555 \
  --params '{"username":"standard_user","password":"secret_sauce","item_name":"Sauce Labs Backpack"}'
```

`--capability` accepts either the artifact's `id` (shown in `catalog`'s
output and inside the artifact JSON) or the artifact's filename.

To see an actual AI agent discover the catalog and choose/invoke a
capability on its own (a real Claude tool-use call, not a script picking
for it):

```bash
python examples/agent_invoke_demo.py
```

This prints which capability Claude chose, the arguments it decided to
pass, and the replay result.

## 5. Human escalation, hands-on

Run discovery or replay with `--headed`. If the agent can't decide what to do
next, or is about to run a step flagged "risky" by `config/policy.json`
(e.g. anything matching `finish`, `remove`, `logout`), it will:

1. print the reason and the current context,
2. leave the **same visible browser window** open and idle,
3. block on a terminal prompt.

You can click/type directly in that window, then type a short note and press
Enter to resume, or type `abort` to stop the run cleanly. This is the whole
handoff mechanism — see `/REPORT.md` section 5 for the design of a fuller
operator console.

## 6. Running without live services

There's no offline mode for discovery (it needs both the live page and the
live Claude API by design — that's the point of the assignment). The
browser-free tests in step 2 are the "no live services" path for verifying
the artifact schema, guardrails, and substitution logic.

## Project layout

```
agent/
  schema.py      typed artifact contract (Locator, Step, Artifact, ...)
  browser.py     element enumeration + robust locator build/resolve
  llm.py         Claude call for the "decide" step
  discovery.py   observe -> decide -> act loop, emits an Artifact
  replay.py      deterministic replay engine, error taxonomy, retry/backoff
  guardrails.py  domain/action allowlist + risky-action classification
  logger.py      structured JSONL logs + screenshot evidence
  escalation.py  human-in-the-loop pause/resume
  catalog.py     exposes saved artifacts as agent-callable tool definitions
cli.py           discover / replay / catalog / invoke commands
examples/agent_invoke_demo.py   a real agent choosing + invoking a capability
config/policy.json
tests/test_logic.py
evidence/        one folder per run (created at runtime)
artifacts/       saved capability artifacts
```