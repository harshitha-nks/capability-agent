"""
Safety guardrails: domain allowlist, action allowlist, and risky-action
classification. Loaded from config/policy.json so the policy is configurable
without touching code.
"""
import json
import re
from urllib.parse import urlparse


class SafetyViolation(Exception):
    pass


class Policy:
    def __init__(self, path: str = "config/policy.json"):
        with open(path) as f:
            data = json.load(f)
        self.allowed_domains = data["allowed_domains"]
        self.allowed_actions = set(data["allowed_actions"])
        self.risky_patterns = [re.compile(p, re.I) for p in data["risky_patterns"]]

    def check_domain(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        if not any(host == d or host.endswith("." + d) for d in self.allowed_domains):
            raise SafetyViolation(f"Domain not on allowlist: {host!r}")

    def check_action(self, action: str) -> None:
        if action not in self.allowed_actions:
            raise SafetyViolation(f"Action not on allowlist: {action!r}")

    def is_risky(self, text: str) -> bool:
        text = text or ""
        return any(p.search(text) for p in self.risky_patterns)
