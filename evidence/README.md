# Evidence

This folder is populated automatically at runtime — one subfolder per run,
named `discover_<id>` or `replay_<id>`, each containing:

- `events.jsonl` — one structured JSON event per line (LLM decisions, actions
  taken, safety checks, outcomes, human interventions).
- `screenshots/` — captured on failure/timeout, and on the final "max steps
  reached" or "checkpoint failed" states.
- `artifact.json` — a copy of the artifact as it existed at the end of that
  discovery run.

**Nothing is checked in here yet.** This repo ships the code, not a
fabricated run — the assignment is explicit that the discovery run has to be
real, and a genuine run needs a live browser and your own Anthropic API key,
neither of which is available in the environment this repo was authored in.

To populate this folder with real evidence, follow `/README.md` section 3:

```bash
python cli.py discover --goal "..." --start-url "https://www.saucedemo.com" \
  --params '...' --secret-params username,password \
  --out artifacts/add_to_cart_and_checkout.json --headed

python cli.py replay --artifact artifacts/add_to_cart_and_checkout.json --params '...'

# and, to capture a business-outcome (non-crash) replay for the error-handling evidence:
python cli.py replay --artifact artifacts/add_to_cart_and_checkout.json \
  --params '{"username":"locked_out_user","password":"secret_sauce","item_name":"Sauce Labs Backpack"}'
```

Each command above will create its own timestamped folder here.
