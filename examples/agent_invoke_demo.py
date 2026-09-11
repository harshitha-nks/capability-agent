"""
Stretch-goal demo: an AI agent is handed the capability catalog as tools,
picks one, and calls it with typed arguments - exactly how a production
agent would invoke a saved capability. Run from the repo root:

    python examples/agent_invoke_demo.py

Requires at least one artifact already saved under artifacts/ (run
`python cli.py discover ...` first) and ANTHROPIC_API_KEY in .env.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anthropic
from dotenv import load_dotenv
from agent.catalog import list_capabilities, invoke_capability

load_dotenv()

MODEL = "claude-sonnet-5"


def main():
    catalog = list_capabilities()
    if not catalog:
        print("No artifacts found in artifacts/ - run `python cli.py discover ...` first.")
        return

    tools = [entry["tool_def"] for entry in catalog]
    client = anthropic.Anthropic()

    user_request = (
        "Reach the checkout overview page for user standard_user "
        "(password secret_sauce) with the Sauce Labs Backpack in the cart."
    )
    print(f"Agent request: {user_request}\n")

    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        tools=tools,
        messages=[{"role": "user", "content": user_request}],
    )

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if not tool_use:
        print("Claude didn't choose to call a capability. Raw response:")
        print(resp.content)
        return

    print(f"Claude chose capability: {tool_use.name}")
    print(f"With arguments: {json.dumps(tool_use.input, indent=2)}\n")

    result = invoke_capability(tool_use.name, tool_use.input, headless=True)
    print("Invocation result:")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()