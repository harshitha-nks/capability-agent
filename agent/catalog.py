"""
Stretch goal: agent-facing capability interface.

Turns every saved artifact in artifacts/ into a small, discoverable,
callable surface - the shape an AI agent (or a person, via the CLI) can
list and invoke by name with typed arguments, without needing to know
there's a Playwright-driven browser underneath. `list_capabilities`
produces Anthropic tool-use style definitions straight from each
artifact's `input_params`, so the schema is the single source of truth for
both the human-readable artifact and the machine-callable tool.
"""
import glob
import os

from .schema import Artifact
from .replay import run_replay

_TYPE_MAP = {"string": "string", "number": "number", "boolean": "boolean"}


def list_capabilities(artifacts_dir: str = "artifacts") -> list[dict]:
    """Return every saved artifact as {capability_name, path, tool_def}."""
    catalog = []
    for path in sorted(glob.glob(os.path.join(artifacts_dir, "*.json"))):
        artifact = Artifact.model_validate_json(open(path).read())
        properties = {
            p.name: {"type": _TYPE_MAP[p.type], "description": p.description or p.name}
            for p in artifact.input_params
        }
        required = [p.name for p in artifact.input_params if p.required]
        catalog.append({
            "capability_name": artifact.id,
            "path": path,
            "tool_def": {
                "name": artifact.id,
                "description": artifact.goal,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return catalog


def invoke_capability(name: str, params: dict, artifacts_dir: str = "artifacts",
                       headless: bool = True) -> dict:
    """Find the artifact whose id (or filename) matches `name` and replay it.
    This is the function an agent-facing API endpoint would wrap directly."""
    for entry in list_capabilities(artifacts_dir):
        if name in (entry["capability_name"], os.path.basename(entry["path"])):
            return run_replay(entry["path"], params, headless=headless)
    return {"status": "failure", "kind": "unknown_capability",
            "error": f"no artifact found matching '{name}'"}