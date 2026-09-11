"""
Replay executes a saved Artifact with no LLM in the loop. Every step's
locator is resolved with its fallback chain; the result is one of three
clearly distinguished kinds (see /REPORT.md section 3):

  - success            goal state verified, declared outputs returned
  - business_outcome   a recognized, expected non-goal state (e.g. "invalid
                        login") - not an error, just a different legitimate
                        result the caller needs to know about
  - failure            something the artifact didn't anticipate, with enough
                        detail (step id, what was tried, screenshot) to debug
"""
import re
import time
import uuid
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

from .schema import Artifact
from .browser import resolve_locator
from .guardrails import Policy, SafetyViolation
from .logger import RunLogger, redact
from .escalation import request_human

MAX_STEP_ATTEMPTS = 2      
RETRY_BACKOFF_SECONDS = 1.5


def substitute(value, params: dict):
    if value is None:
        return None
    def repl(m):
        return str(params.get(m.group(1), m.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", repl, value)


def run_replay(artifact_path: str, params: dict, headless: bool = True,
               auto_approve_risky: bool = False) -> dict:
    with open(artifact_path) as f:
        artifact = Artifact.model_validate_json(f.read())

    for p in artifact.input_params:
        if p.required and p.name not in params:
            return {"status": "failure", "kind": "bad_params",
                    "error": f"missing required param: {p.name}"}

    run_id = f"replay_{uuid.uuid4().hex[:8]}"
    logger = RunLogger(run_id)
    policy = Policy()
    policy.check_domain(artifact.start_url)

    log_params = {k: redact(v, _is_secret(artifact, k)) for k, v in params.items()}
    logger.log("replay_start", artifact=artifact.id, params=log_params)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_context().new_page()
        page.on("dialog", lambda dialog: _handle_dialog(dialog, logger))
        try:
            for step in artifact.steps:
                _run_step(page, step, params, policy, logger, auto_approve_risky)
                outcome = _match_known_outcome(page, artifact, logger)
                if outcome:
                    logger.log("replay_business_outcome", outcome=outcome.name)
                    browser.close()
                    return {"status": "business_outcome", "outcome": outcome.name,
                            "description": outcome.description, "evidence": logger.dir}

            result = _check_checkpoint(page, artifact, logger)
            if result["status"] != "success":
                path = logger.screenshot_path("checkpoint_failed")
                page.screenshot(path=path)
                result["evidence"] = logger.dir
                browser.close()
                return result

            outputs = _extract_outputs(page, artifact, logger)
            logger.log("replay_success", outputs=outputs)
            browser.close()
            return {"status": "success", "outputs": outputs, "evidence": logger.dir}

        except SafetyViolation as e:
            logger.log("safety_violation", error=str(e))
            browser.close()
            return {"status": "failure", "kind": "safety_violation",
                    "error": str(e), "evidence": logger.dir}

        except LookupError as e:
            path = logger.screenshot_path("failure")
            page.screenshot(path=path)
            logger.log("hard_failure", kind="locator_not_found", error=str(e), screenshot=path)
            browser.close()
            return {"status": "failure", "kind": "locator_not_found",
                    "error": str(e), "evidence": logger.dir}

        except Exception as e:
            try:
                path = logger.screenshot_path("failure")
                page.screenshot(path=path)
            except Exception:
                path = None
            logger.log("hard_failure", kind="unexpected_error", error=str(e), screenshot=path)
            browser.close()
            return {"status": "failure", "kind": "unexpected_error",
                    "error": str(e), "evidence": logger.dir}


def _is_secret(artifact: Artifact, name: str) -> bool:
    return any(p.name == name and p.secret for p in artifact.input_params)


def _run_step(page, step, params, policy, logger, auto_approve_risky):
    if step.action == "goto":
        url = substitute(step.url, params)
        policy.check_domain(url)
        page.goto(url)
        logger.log("step", id=step.id, action="goto", url=url)
        return

    policy.check_action(step.action)
    if step.risky and not auto_approve_risky:
        request_human(logger, f"Risky step requires approval: {step.description}",
                       {"step": step.id})

    # Transient conditions (a slow load, a momentarily-not-yet-visible element)
    # get one retry with backoff before we treat this as a hard failure.
    last_err = None
    for attempt in range(1, MAX_STEP_ATTEMPTS + 1):
        try:
            loc = resolve_locator(page, step.locator.model_dump())
            _perform_action(loc, step, params)
            logger.log("step", id=step.id, action=step.action, attempt=attempt)
            return
        except (LookupError, PWTimeoutError) as e:
            last_err = e
            logger.log("step_retry", id=step.id, attempt=attempt, error=str(e))
            if attempt < MAX_STEP_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)

    raise LookupError(f"step {step.id} ({step.action}): {last_err}")


def _perform_action(loc, step, params):
    if step.action == "click":
        loc.click()
    elif step.action == "type":
        loc.fill(substitute(step.value, params))
    elif step.action == "select":
        loc.select_option(label=substitute(step.value, params))
    elif step.action == "wait_for":
        loc.wait_for(state="visible")


def _handle_dialog(dialog, logger):
    """Unexpected browser dialogs (alert/confirm/prompt) are a recoverable
    condition, not a hard failure: log what appeared and dismiss it so the
    run can continue rather than hanging forever waiting on a native popup."""
    logger.log("dialog_auto_dismissed", dialog_type=dialog.type, message=dialog.message)
    dialog.dismiss()


def _match_known_outcome(page, artifact: Artifact, logger):
    for outcome in artifact.known_outcomes:
        try:
            resolve_locator(page, outcome.locator.model_dump())
            return outcome
        except Exception:
            continue
    return None


def _check_checkpoint(page, artifact: Artifact, logger) -> dict:
    cp = artifact.checkpoint
    if cp.url_contains and cp.url_contains not in page.url:
        return {"status": "failure", "kind": "checkpoint_failed",
                "error": f"expected url containing '{cp.url_contains}', got '{page.url}'"}
    if cp.expected_text and cp.expected_text not in page.content():
        return {"status": "failure", "kind": "checkpoint_failed",
                "error": f"expected text '{cp.expected_text}' not found on page"}
    logger.log("checkpoint_verified")
    return {"status": "success"}


def _extract_outputs(page, artifact: Artifact, logger) -> dict:
    outputs = {}
    for out in artifact.outputs:
        loc = resolve_locator(page, out.locator.model_dump())
        outputs[out.name] = loc.inner_text() if out.attribute == "text" else loc.input_value()
    return outputs