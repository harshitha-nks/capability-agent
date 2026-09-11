"""
The "perceive/act" seam.

`enumerate_elements` is our stand-in for an accessibility-tree read: it
collects every visible interactive element and a compact description of it,
which is what gets shown to the LLM during discovery. It works whether or
not the page has clean test ids, which matters for the "no clean DOM" case
described in the brief.

`build_locator_spec` turns one concrete element into a portable, replayable
locator with fallbacks (test id > accessible name/role > visible text > css
id), ordered roughly by robustness for the surface we're on.

`resolve_locator` is the replay-time counterpart: try the primary strategy,
then each fallback in order, and fail loudly (with detail) only once all of
them are exhausted.
"""
from playwright.sync_api import Page

INTERACTIVE_SELECTOR = (
    "a, button, input, select, textarea, "
    "[role=button], [role=link], [role=checkbox], [onclick]"
)


class Element:
    def __init__(self, index, handle, tag, text, attrs):
        self.index = index
        self.handle = handle
        self.tag = tag
        self.text = text
        self.attrs = attrs


def enumerate_elements(page: Page, limit: int = 60):
    handles = page.query_selector_all(INTERACTIVE_SELECTOR)
    elements = []
    idx = 0
    for h in handles:
        try:
            if not h.is_visible():
                continue
            tag = h.evaluate("e => e.tagName.toLowerCase()")
            text = (h.inner_text() or "").strip()[:80]
            attrs = h.evaluate(
                "e => ({id: e.id, name: e.name, type: e.type, "
                "placeholder: e.placeholder, "
                "dataTest: e.getAttribute('data-test') || e.getAttribute('data-testid'), "
                "role: e.getAttribute('role'), ariaLabel: e.getAttribute('aria-label')})"
            )
            elements.append(Element(idx, h, tag, text, attrs))
            idx += 1
            if idx >= limit:
                break
        except Exception:
            continue
    return elements


def describe_elements(elements) -> str:
    lines = []
    for e in elements:
        a = e.attrs
        bits = [f"[{e.index}] <{e.tag}>"]
        if e.text:
            bits.append(f'text="{e.text}"')
        if a.get("dataTest"):
            bits.append(f'data-test="{a["dataTest"]}"')
        if a.get("placeholder"):
            bits.append(f'placeholder="{a["placeholder"]}"')
        if a.get("name"):
            bits.append(f'name="{a["name"]}"')
        if a.get("type"):
            bits.append(f'type="{a["type"]}"')
        if a.get("role"):
            bits.append(f'role="{a["role"]}"')
        lines.append(" ".join(bits))
    return "\n".join(lines)


def build_locator_spec(el: Element) -> dict:
    a = el.attrs
    candidates = []
    if a.get("dataTest"):
        candidates.append({"strategy": "data-test", "value": a["dataTest"]})
    if a.get("ariaLabel"):
        role = a.get("role") or el.tag
        candidates.append({"strategy": "role", "value": f'{role}|{a["ariaLabel"]}'})
    if el.text:
        candidates.append({"strategy": "text", "value": el.text})
    if a.get("id"):
        candidates.append({"strategy": "css", "value": f'#{a["id"]}'})
    if not candidates:
        candidates.append({"strategy": "css", "value": el.tag})
    primary, fallbacks = candidates[0], candidates[1:]
    primary = dict(primary)
    primary["fallbacks"] = fallbacks
    return primary


def resolve_locator(page: Page, spec: dict):
    tried = [spec] + list(spec.get("fallbacks", []))
    last_err = None
    for cand in tried:
        try:
            loc = _to_locator(page, cand)
            loc.first.wait_for(state="visible", timeout=4000)
            return loc.first
        except Exception as e:
            last_err = e
            continue
    raise LookupError(f"could not resolve any locator in {tried}: {last_err}")


def _to_locator(page: Page, cand: dict):
    strat, val = cand["strategy"], cand["value"]
    if strat == "data-test":
        return page.locator(f'[data-test="{val}"], [data-testid="{val}"]')
    if strat == "css":
        return page.locator(val)
    if strat == "text":
        return page.get_by_text(val, exact=False)
    if strat == "role":
        role, label = val.split("|", 1)
        return page.get_by_role(role, name=label)
    if strat == "xpath":
        return page.locator(f"xpath={val}")
    raise ValueError(f"unknown locator strategy: {strat}")
