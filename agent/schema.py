"""
Typed, versioned schema for a recorded "capability" artifact.

Design intent (see /REPORT.md section 2 for the full rationale):
- A Locator is never a single brittle selector: it's a primary strategy plus an
  ordered list of fallback strategies, so replay can survive small UI drift.
- Step.value may contain {{param_name}} placeholders, so a flow recorded once
  (e.g. with member 12345) can be replayed with any member id.
- KnownOutcome lets replay tell "no such member" (a legitimate business result)
  apart from a real crash, without guessing.
"""
from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import uuid
import datetime


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Locator(BaseModel):
    """How to find one element on the page, with fallbacks tried in order."""
    strategy: Literal["data-test", "role", "text", "css", "xpath"]
    value: str
    fallbacks: List["Locator"] = Field(default_factory=list)


Locator.model_rebuild()


class InputParam(BaseModel):
    """A typed input the calling agent must supply per invocation."""
    name: str
    type: Literal["string", "number", "boolean"] = "string"
    required: bool = True
    secret: bool = False  # never logged or persisted in plaintext
    description: str = ""


class OutputField(BaseModel):
    """A typed value extracted from the page once the checkpoint is reached."""
    name: str
    type: Literal["string", "number", "boolean"] = "string"
    description: str = ""
    locator: Locator
    attribute: Literal["text", "value"] = "text"


class KnownOutcome(BaseModel):
    """A recognizable page state that is a legitimate result, not a failure."""
    name: str
    description: str
    locator: Locator
    kind: Literal["business_outcome", "recoverable"] = "business_outcome"


class Step(BaseModel):
    id: str = Field(default_factory=lambda: _id("step"))
    action: Literal["goto", "click", "type", "select", "wait_for", "extract"]
    locator: Optional[Locator] = None
    value: Optional[str] = None   # literal, or "{{param_name}}"
    url: Optional[str] = None     # only for action == "goto"
    description: str = ""
    risky: bool = False           # flagged by guardrails at record time


class Checkpoint(BaseModel):
    """Proof the goal state was actually reached, not just that clicks ran."""
    description: str
    locator: Optional[Locator] = None
    url_contains: Optional[str] = None
    expected_text: Optional[str] = None


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: _id("cap"))
    name: str
    version: int = 1
    created_at: str = Field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    goal: str
    start_url: str
    input_params: List[InputParam] = Field(default_factory=list)
    steps: List[Step] = Field(default_factory=list)
    outputs: List[OutputField] = Field(default_factory=list)
    checkpoint: Checkpoint
    known_outcomes: List[KnownOutcome] = Field(default_factory=list)
    discovery_run_id: Optional[str] = None
