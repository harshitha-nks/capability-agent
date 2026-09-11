import json
import uuid
from playwright.sync_api import sync_playwright

from .schema import Artifact, Step, Locator, InputParam, OutputField, Checkpoint
from .browser import enumerate_elements, describe_elements, build_locator_spec
from .llm import decide
from .guardrails import Policy, SafetyViolation
from .logger import RunLogger, redact
from .escalation import request_human

MAX_STEPS = 20


def run_discovery(goal: str, start_url: str, params: dict, secret_params: set,
                   out_path: str, headless: bool = False) -> Artifact:
    run_id = f"discover_{uuid.uuid4().hex[:8]}"
    logger = RunLogger(run_id)
    policy = Policy()
    policy.check_domain(start_url)
    logger.log("run_start", goal=goal, start_url=start_url,
               params={k: redact(v, k in secret_params) for k, v in params.items()})

    steps: list[Step] = []
    history: list[str] = []
    outputs: list[OutputField] = []
    checkpoint = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        page = browser.new_context().new_page()
        page.goto(start_url)
        steps.append(Step(action="goto", url=start_url, description="Open start page"))
        logger.log("action", action="goto", url=start_url)

        reached_goal = False
        for i in range(MAX_STEPS):
            elements = enumerate_elements(page)
            desc = describe_elements(elements)
            decision = decide(goal, params, page.url, desc, history)
            logger.log("llm_decision", step=i, decision=decision)

            action = decision.get("action")

            if action == "finish":
                for name, spec in (decision.get("outputs") or {}).items():
                    el = elements[spec["index"]]
                    loc_spec = build_locator_spec(el)
                    outputs.append(OutputField(
                        name=name, type="string", locator=Locator(**loc_spec),
                        attribute=spec.get("attribute", "text"),
                    ))
                    logger.log("output_captured", name=name)
                checkpoint = Checkpoint(description="Goal reached",
                                         url_contains=page.url.split("?")[0])
                logger.log("goal_reached", url=page.url)
                reached_goal = True
                break

            if action == "fail":
                logger.log("agent_stuck", reasoning=decision.get("reasoning"))
                note = request_human(logger, decision.get("reasoning", "agent stuck"),
                                      {"url": page.url, "step": i})
                history.append(f"[human] {note}")
                continue

            if action == "goto":
                policy.check_domain(decision["url"])
                page.goto(decision["url"])
                steps.append(Step(action="goto", url=decision["url"],
                                   description=decision.get("reasoning", "")))
                history.append(f"goto {decision['url']}")
                continue

            policy.check_action(action)
            el = elements[decision["index"]]
            loc_spec = build_locator_spec(el)
            risky = policy.is_risky(f"{el.text} {json.dumps(el.attrs)}")
            if risky:
                request_human(logger, f"Risky action about to run: {action} on '{el.text}'",
                               {"url": page.url})

            if action == "click":
                el.handle.click()
                steps.append(Step(action="click", locator=Locator(**loc_spec), risky=risky,
                                   description=decision.get("reasoning", "")))
                history.append(f"click [{el.index}] {el.text}")

            elif action == "type":
                text = decision.get("text", "")
                el.handle.fill(text)
                stored_value = text
                for pname, pval in params.items():
                    if pval == text:
                        stored_value = "{{" + pname + "}}"
                        break
                steps.append(Step(action="type", locator=Locator(**loc_spec), value=stored_value,
                                   risky=risky, description=decision.get("reasoning", "")))
                shown = redact(text, any(text == params.get(p) for p in secret_params))
                history.append(f"type [{el.index}] '{shown}'")

            elif action == "select":
                text = decision.get("text", "")
                el.handle.select_option(label=text)
                steps.append(Step(action="select", locator=Locator(**loc_spec), value=text,
                                   risky=risky, description=decision.get("reasoning", "")))
                history.append(f"select [{el.index}] '{text}'")

            logger.log("action", action=action, index=decision.get("index"))

        if not reached_goal:
            path = logger.screenshot_path("max_steps_reached")
            page.screenshot(path=path)
            logger.log("max_steps_reached", screenshot=path)
            browser.close()
            raise SystemExit("Discovery hit max steps without reaching the goal.")

        logger.log("run_complete")
        browser.close()

    input_params = [InputParam(name=n, type="string", secret=(n in secret_params))
                     for n in params]
    artifact = Artifact(
        name=goal[:60],
        goal=goal,
        start_url=start_url,
        input_params=input_params,
        steps=steps,
        outputs=outputs,
        checkpoint=checkpoint,
        discovery_run_id=run_id,
    )
    with open(out_path, "w") as f:
        f.write(artifact.model_dump_json(indent=2))
    with open(logger.artifact_path(), "w") as f:
        f.write(artifact.model_dump_json(indent=2))
    print(f"Artifact saved to {out_path}")
    print(f"Evidence saved to {logger.dir}/")
    return artifact
