"""
The "decide" half of observe -> decide -> act. One call per step: we show
Claude the goal, the supplied inputs, the current URL, and a numbered list of
interactive elements, and ask for exactly one next action as JSON.
"""
import json
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are a UI automation agent. You are given a GOAL, the current URL, \
a numbered list of interactive elements visible on the page, and the history of actions \
you've already taken. Choose exactly ONE next action to move closer to the goal.

Respond with ONLY a JSON object, no prose, no markdown fences, matching this shape:
{"action": "click|type|select|goto|finish|fail",
 "index": <int, required for click/type/select>,
 "text": <string, required for type/select - the value to enter>,
 "url": <string, required for goto>,
 "reasoning": "<one short sentence>",
 "outputs": {"<name>": {"index": <int>, "attribute": "text"}}  // only for finish
}

Rules:
- Use "type" to fill inputs, "click" for buttons/links, "select" for <select> dropdowns.
- Only use values given to you in AVAILABLE INPUT VALUES for typing - never invent
  credentials or data.
- Call "finish" once the goal is verifiably reached; include any requested outputs by
  pointing at the element index that currently displays that value.
- Call "fail" if you are stuck and cannot safely proceed - explain why in reasoning.
- Never reference an index that is not in the element list.
"""


def decide(goal: str, params: dict, url: str, elements_desc: str, history: list) -> dict:
    client = anthropic.Anthropic()
    history_text = "\n".join(history[-15:]) or "(none yet)"
    user_msg = (
        f"GOAL: {goal}\n"
        f"AVAILABLE INPUT VALUES: {json.dumps(params)}\n"
        f"CURRENT URL: {url}\n"
        f"INTERACTIVE ELEMENTS:\n{elements_desc}\n"
        f"ACTIONS TAKEN SO FAR:\n{history_text}\n"
    )    
    resp = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.strip("`")
    if text.startswith("json"):
        text = text[4:].strip()
    if not text:
        raise RuntimeError(f"Empty response from model. stop_reason={resp.stop_reason}, raw content={resp.content}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model did not return valid JSON. Raw text was:\n{text}") from e
