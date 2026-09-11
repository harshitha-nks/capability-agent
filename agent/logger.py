"""
Structured, append-only event log per run, plus a screenshots/ folder for
richer failure evidence. One directory per run under evidence/<run_id>/.
"""
import json
import os
import datetime

SECRET_MASK = "***"


class RunLogger:
    def __init__(self, run_id: str, base_dir: str = "evidence"):
        self.run_id = run_id
        self.dir = os.path.join(base_dir, run_id)
        os.makedirs(self.dir, exist_ok=True)
        os.makedirs(os.path.join(self.dir, "screenshots"), exist_ok=True)
        self.events_path = os.path.join(self.dir, "events.jsonl")

    def log(self, event_type: str, **data):
        entry = {
            "ts": datetime.datetime.utcnow().isoformat(),
            "run_id": self.run_id,
            "event": event_type,
            **data,
        }
        with open(self.events_path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def screenshot_path(self, name: str) -> str:
        return os.path.join(self.dir, "screenshots", f"{name}.png")

    def artifact_path(self) -> str:
        return os.path.join(self.dir, "artifact.json")


def redact(value: str, secret: bool) -> str:
    return SECRET_MASK if secret else value
