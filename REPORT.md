# Design Report

## 1. Architecture

The project is one Python codebase with two commands: `discover` and `replay`.
`discover` runs Claude in a loop against a real, live browser — look at the
page, decide what to do, do it, repeat. `replay` runs later with no AI
involved at all — it just replays the recorded steps. Both share the same
code for touching the browser, checking safety rules, and writing logs, so
that logic only exists in one place.

I kept this as a single script instead of a service with a job queue. The
work is naturally one-step-at-a-time anyway (ask Claude, wait, act, repeat),
and a single run is cheap and fast, so a queue would just be extra
infrastructure with nothing to show for it.

To "see" the page, instead of taking a screenshot and asking Claude to guess
pixel coordinates, I list out every clickable/typeable element on the page
(button text, labels, ids) and number them. Claude picks an action by
number. This works even on pages with messy HTML and no test IDs, and it's
cheaper and more reliable than screenshots.

## 2. Artifact schema

The core idea: a saved artifact isn't just a transcript of what happened —
it's meant to be *called*, like a function. So it has clearly separated
parts:

- **Inputs and outputs** — named and typed, so a calling agent knows exactly
  what to send in and what it'll get back. Anything marked `secret` (like a
  password) never gets written to disk or logs in plain text.
- **Steps** — the recorded clicks/types, in order. A typed value can be a
  placeholder like `{{username}}` instead of the literal value, so the same
  recording works for any user, not just the one it was recorded with.
- **Locators with fallbacks** — instead of one fragile selector per element,
  each one has a backup plan: try the test ID first, then the visible text,
  then a CSS id. So a small page change doesn't automatically break replay.
- **Checkpoint** — an explicit check that we actually reached the goal (e.g.
  the URL contains `checkout-step-two`), not just "nothing crashed."
- **Known outcomes** — page states that are expected results, not errors —
  like a "wrong password" banner. This is what lets replay say "this is a
  normal rejection" instead of treating it as a broken run.

It's all built with Pydantic, so a saved artifact validates itself on load
and is easy for a person (or another AI) to read top to bottom.

## 3. Determinism & error handling

Replay is deterministic because nothing is left to a model's judgment — every
decision was already made once during discovery. Locators are always tried
in the same order, and every interaction waits for the element to actually
be visible before acting, so it doesn't race a slow page.

Every replay ends in one of three clearly labeled outcomes:

- **success** — goal reached, outputs returned.
- **business_outcome** — the page matched a known, expected non-goal state
  (like "no such member" or "wrong password"). Not a failure, just a
  different legitimate result.
- **failure** — something unexpected, tagged with what kind of problem it
  was (locator never appeared, checkpoint didn't match, safety rule
  violated), which step it happened on, and a screenshot.

One real gap I found while testing: `known_outcomes` only gets populated if
you add it by hand after the fact — the discovery loop doesn't teach itself
to recognize an error banner automatically. I saw this firsthand: replaying
with a locked-out test account first came back as a confusing
"couldn't find the add-to-cart button" failure, two steps after the actual
problem (a rejected login). Once I manually added the login-error banner as
a known outcome, replay correctly reported it as a clean `business_outcome`
instead. Worth fixing properly with more time (see Cuts).

I didn't build retry/backoff for slow-loading pages beyond the locator's own
short wait, or auto-handling of unexpected popup dialogs — both are small,
well-understood additions, just not needed to prove out the design here.

## 4. Heterogeneity & multi-tenant

The one seam that matters: everything above `browser.py` only talks in terms
of "numbered elements" and "locators with a strategy" — it has no idea it's
looking at a website specifically. To support a legacy app with no test IDs,
the existing fallback chain (test id → role/label → visible text → CSS)
already handles that. To support a desktop app, you'd write a new "observer"
that reads the OS accessibility tree instead of the DOM but returns the same
shape of data — nothing in the artifact schema or replay engine would need
to change, you'd just add a new locator strategy type.

For reusing one artifact across many customers running the same underlying
product: I didn't build this, but the schema has room for it. The plan would
be to let an artifact have a "base" version plus small per-tenant overrides
(a different button label, an extra field) rather than re-recording from
scratch per tenant. You'd detect when a tenant's version has drifted too far
by replaying against it and seeing how often the fallback locators are the
ones saving the day — if a step increasingly needs its second or third
fallback to succeed, that's an early warning the base recording is going
stale for that tenant.

## 5. Escalation & handoff

Three things trigger a human being pulled in: Claude explicitly says "I'm
stuck," a step is flagged risky (matches words like "finish," "remove,"
"logout" in the safety config) and hasn't been pre-approved, or replay hits
a failure it can't make sense of.

The handoff itself is deliberately simple: the browser runs in a normal,
visible window (not headless), so there's only ever one session — the human
and the automation are looking at, and can act in, the exact same window.
When it needs help, the script just pauses and prints what's wrong; you can
click around in that same window yourself, then type a short note in the
terminal and hit Enter to let it continue (or type "abort" to stop
cleanly).

A real production version of this would swap the "pause and wait for
Enter" part for a proper queue and a web-based operator view (so someone
isn't stuck at a terminal), but the underlying contract — pause, hand
context to a human, resume or abort — would stay exactly the same.

## 6. Safety

All the rules live in one config file, so they're easy to review and change
without touching code:

- **Domain allowlist** — nothing can navigate outside a fixed list of
  approved sites. Trying to leave it is blocked and reported clearly.
- **Action allowlist** — only a fixed set of actions (click, type, select,
  etc.) are possible in the first place.
- **Risky actions need a human** — anything matching words like "finish,"
  "remove," or "logout" pauses for a person to confirm before running,
  rather than being silently blocked. I chose confirm-over-block because the
  whole point of some flows is to reach right up to a final action and let a
  person decide whether to actually take it. A flag lets you run fully
  unattended once you trust a specific artifact.
- **Redaction** — anything marked as a secret input (like a password) is
  never written to disk or logs as plain text — only as a placeholder.

**Where this is weak:** the risky-action check is just keyword matching. It
won't catch a dangerous button that happens to be worded differently, and
someone could rename a button to dodge it. It's a reasonable first line of
defense, not a guarantee.

## 7. What I left out, and why

- **A real operator dashboard** — out of scope per the brief. What I built
  (pause the shared browser window, resume from the terminal) is the
  minimal real version of the same idea.
- **Multi-tenant overrides** — designed, not built. No second tenant to test
  it against without inventing one.
- **Retry/backoff for flaky loads, and auto-dismissing popups** — small,
  well-understood additions I didn't need for this demo.
- **Auto-discovering "known outcomes" during the agent loop** — right now
  you have to notice an error state and add it to the artifact by hand
  afterward, which I actually ran into while testing (see section 3). With
  more time I'd have the discovery loop flag "this looks like an error
  state, want to remember it?" on its own.
- **Confidence scoring / approval gates before unattended replay** — one of
  the optional extras; skipped so the required core stayed solid instead of
  spreading effort across an optional feature too.
- **Exposing artifacts as a callable API for other agents** — `run_replay()`
  is already a clean function; wrapping it as an endpoint would be a short
  follow-up, not a rebuild.