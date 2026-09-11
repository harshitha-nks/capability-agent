"""
Minimal but real human handoff.

The browser is launched non-headless (a real, visible window) and the
automation and the human share that *same* window/session - there is no
second browser to hand off to. When the automation needs a human, it:
  1. logs the intervention request with full context (reason, url, step),
  2. blocks and prints instructions,
  3. lets the human act directly in the visible window,
  4. waits for the human to type a short note and press Enter to resume
     (or type "abort" to stop the run cleanly).

This is the whole control-transfer model: "control" is just "whoever is
allowed to move the mouse right now," and the block/prompt is the seam.
A fuller version would swap the input() for a message on a queue/socket
that a real operator console listens on - see /REPORT.md section 5.
"""


def request_human(logger, reason: str, context: dict) -> str:
    logger.log("intervention_requested", reason=reason, context=context)
    print("\n=== HUMAN INTERVENTION REQUIRED ===")
    print(f"Reason: {reason}")
    print(f"Context: {context}")
    print("The browser window is visible - you may act directly in it.")
    note = input("Describe what you did, then press Enter to resume (or type 'abort'): ")
    if note.strip().lower() == "abort":
        logger.log("run_aborted_by_human")
        raise SystemExit("Run aborted by human operator.")
    logger.log("human_action", note=note)
    return note
