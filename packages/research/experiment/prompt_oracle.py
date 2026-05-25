"""Deterministic TestPrompt-to-RoboGrammar oracles.

These oracles are intentionally simple and explicit. They give the research
layer a stable answer key for trace debugging and strategy comparisons, while
leaving production generation free to use richer LLM-driven graphs.
"""

from __future__ import annotations

from packages.research.experiment.types import TestPromptLabel


def infer_expected_robo_grammar(
    prompt: str,
    label: TestPromptLabel | None = None,
) -> dict[str, list[str]]:
    """Infer an expected structural-rule sketch for a registered TestPrompt."""

    text = prompt.lower()
    body = _body_rule(text, label)
    return {"S": body}


def _body_rule(prompt: str, label: TestPromptLabel | None) -> list[str]:
    climbing = _has_any(prompt, ("climb", "stair", "ladder", "rock", "rung", "slope"))
    crawling = _has_any(prompt, ("crawl", "duct", "pipe", "vent", "under", "low", "squeeze"))
    manipulation = _has_any(
        prompt,
        (
            "arm",
            "grip",
            "pick",
            "shelf",
            "button",
            "door",
            "tool",
            "object",
            "sample",
            "valve",
            "place",
            "retrieve",
            "trash",
            "clean",
        ),
    )
    payload = _has_any(prompt, ("carry", "payload", "package", "tray", "medicine", "tool"))
    sensing = _has_any(
        prompt,
        (
            "inspect",
            "camera",
            "sensor",
            "map",
            "patrol",
            "monitor",
            "video",
            "survey",
            "observe",
            "scout",
        ),
    )
    stabilizer = _has_any(prompt, ("stable", "stability", "balance", "level", "wind", "gust"))

    if _has_any(prompt, ("quadruped", "four legs", "four-legged", "4-legged")):
        pair = "CLIMBING_LEG_PAIR" if climbing else "LEG_PAIR"
        nodes = ["BODY", pair, pair]
        if _has_any(prompt, ("tail", "spine", "forest", "underbrush")) or climbing:
            nodes.append("TAIL")
        return _with_task_modules(nodes, manipulation, payload, sensing, stabilizer)

    if _has_any(prompt, ("hexapod", "six legs", "six-legged", "6-legged", "tripod gait")):
        pair = "CLIMBING_LEG_PAIR" if climbing else "LEG_PAIR"
        return _with_task_modules(["BODY", pair, pair, pair], manipulation, payload, sensing, stabilizer)

    if _has_any(prompt, ("biped", "humanoid", "ostrich", "two long legs", "walking assistance")):
        nodes = ["BODY", "LEG", "LEG"]
        if "humanoid" in prompt or manipulation:
            nodes.append("ARM_PAIR")
        return _with_task_modules(nodes, manipulation, payload, sensing, stabilizer)

    if _has_any(prompt, ("snake", "sidewind", "pipe", "duct", "vent", "tunnel", "crawlspace")):
        nodes = ["BODY_CHAIN", "BODY_SEG", "BODY_SEG", "BODY_SEG"]
        if sensing:
            nodes.append("SENSOR_HEAD")
        return _with_task_modules(nodes, manipulation, payload, sensing=False, stabilizer=stabilizer)

    if _has_any(prompt, ("centipede", "many short legs", "many legs")):
        return _with_task_modules(
            ["BODY_CHAIN", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR", "LEG_PAIR"],
            manipulation,
            payload,
            sensing,
            stabilizer,
        )

    if _has_any(prompt, ("lizard", "sprawling", "adhesive")):
        return _with_task_modules(
            ["BODY", "SPRAWLED_LEG_PAIR", "SPRAWLED_LEG_PAIR", "TAIL"],
            manipulation,
            payload,
            sensing,
            stabilizer,
        )

    if _has_any(prompt, ("bird", "wing", "hopping", "gaps")):
        return _with_task_modules(
            ["BODY", "LEG_PAIR", "WING_PAIR", "TAIL"],
            manipulation,
            payload,
            sensing,
            stabilizer,
        )

    if _has_any(prompt, ("wheel", "corridor", "factory floor", "flat", "patrol")):
        return _with_task_modules(["BODY", "WHEEL_PAIR"], manipulation, payload, sensing, stabilizer)

    if _has_any(prompt, ("track", "tracked", "crawler", "construction floor")):
        return _with_task_modules(["BODY", "TRACK_PAIR"], manipulation, payload, sensing, stabilizer)

    if label == "infer-morphology-family" or _has_any(prompt, ("family", "families", "variants", "alternatives")):
        return _with_task_modules(
            ["BODY", "LEG_PAIR", "WHEEL_PAIR", "BODY_CHAIN"],
            manipulation,
            payload,
            sensing,
            stabilizer=True,
        )

    if crawling:
        return _with_task_modules(["LOW_PROFILE_BODY", "BODY_SEG", "CONTACT_PAD"], manipulation, payload, sensing, stabilizer)

    if climbing:
        return _with_task_modules(["BODY", "CLIMBING_LEG_PAIR", "CLIMBING_LEG_PAIR"], manipulation, payload, sensing, stabilizer=True)

    base = ["BODY", "APPENDAGE_PAIR"] if label == "open-ended" else ["BODY"]
    return _with_task_modules(base, manipulation, payload, sensing, stabilizer)


def _with_task_modules(
    nodes: list[str],
    manipulation: bool,
    payload: bool,
    sensing: bool,
    stabilizer: bool,
) -> list[str]:
    result = list(nodes)
    if manipulation:
        result.append("MANIPULATION_MODULE")
    if payload:
        result.append("PAYLOAD_BAY")
    if sensing:
        result.append("SENSOR_MAST")
    if stabilizer:
        result.append("STABILIZER")
    return _dedupe_preserving_counts(result)


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _dedupe_preserving_counts(nodes: list[str]) -> list[str]:
    # Repeated limb-pair nodes carry count information and must stay repeated.
    counted = {"LEG_PAIR", "CLIMBING_LEG_PAIR", "SPRAWLED_LEG_PAIR", "BODY_SEG", "LEG"}
    seen: set[str] = set()
    result: list[str] = []
    for node in nodes:
        if node in counted or node not in seen:
            result.append(node)
            seen.add(node)
    return result
