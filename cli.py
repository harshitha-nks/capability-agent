import argparse
import json
import sys

from agent.discovery import run_discovery
from agent.replay import run_replay


def main():
    p = argparse.ArgumentParser(description="Capability agent: discover and replay UI flows.")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="Run an LLM-driven discovery pass and save an artifact.")
    d.add_argument("--goal", required=True)
    d.add_argument("--start-url", required=True)
    d.add_argument("--params", default="{}", help='JSON dict, e.g. \'{"username":"standard_user"}\'')
    d.add_argument("--secret-params", default="", help="comma-separated param names to redact, e.g. username,password")
    d.add_argument("--out", required=True, help="path to write the artifact JSON")
    d.add_argument("--headed", action="store_true", help="show the browser window (recommended)")

    r = sub.add_parser("replay", help="Deterministically replay a saved artifact.")
    r.add_argument("--artifact", required=True)
    r.add_argument("--params", default="{}")
    r.add_argument("--headed", action="store_true")
    r.add_argument("--auto-approve-risky", action="store_true",
                    help="skip human confirmation on risky steps (unattended mode)")

    args = p.parse_args()

    if args.cmd == "discover":
        params = json.loads(args.params)
        secrets = {s for s in args.secret_params.split(",") if s}
        run_discovery(args.goal, args.start_url, params, secrets, args.out,
                      headless=not args.headed)

    elif args.cmd == "replay":
        params = json.loads(args.params)
        result = run_replay(args.artifact, params, headless=not args.headed,
                            auto_approve_risky=args.auto_approve_risky)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] in ("success", "business_outcome") else 1)


if __name__ == "__main__":
    main()
