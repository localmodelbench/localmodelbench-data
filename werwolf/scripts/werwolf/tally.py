from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> dict | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        obj = json.loads(stripped[start : end + 1])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def match_name(raw: object, valid: list[str]) -> str | None:
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().strip('"').strip("'").rstrip(".")
    for name in valid:
        if name.lower() == candidate.lower():
            return name
    for name in valid:
        if name.lower() in candidate.lower() and len(candidate) <= len(name) + 4:
            return name
    return None


def parse_vote(text: str, valid: list[str]) -> tuple[str | None, str, str | None]:
    """Returns (matched_name_or_None, reason, error)."""
    obj = extract_json_object(text)
    if obj is None:
        return None, "", "no_json"
    name = match_name(obj.get("vote"), valid)
    if name is None:
        return None, str(obj.get("reason") or ""), f"invalid_target:{obj.get('vote')!r}"
    return name, str(obj.get("reason") or ""), None


def parse_named_field(text: str, field: str, valid: list[str]) -> tuple[str | None, str | None]:
    obj = extract_json_object(text)
    if obj is None:
        return None, "no_json"
    name = match_name(obj.get(field), valid)
    if name is None:
        return None, f"invalid_target:{obj.get(field)!r}"
    return name, None


def parse_witch_action(text: str, victim: str | None, alive_others: list[str],
                       heal_left: bool, poison_left: bool) -> tuple[str, str | None, str | None]:
    """Returns (action, target_or_None, error)."""
    obj = extract_json_object(text)
    if obj is None:
        return "none", None, "no_json"
    action = str(obj.get("action") or "none").strip().lower()
    if action == "heal":
        if not heal_left or not victim:
            return "none", None, "heal_unavailable"
        return "heal", victim, None
    if action == "poison":
        if not poison_left:
            return "none", None, "poison_unavailable"
        target = match_name(obj.get("target"), alive_others)
        if target is None:
            return "none", None, f"invalid_target:{obj.get('target')!r}"
        return "poison", target, None
    return "none", None, None


def cap_words(text: str, max_words: int = 120) -> tuple[str, bool]:
    words = text.split()
    if len(words) <= max_words:
        return text, False
    return " ".join(words[:max_words]) + " …", True


WOLF_LEAK_RES = [
    re.compile(r"\b(i am|i'm|we are|we're)\s+(the\s+|a\s+)?(werwolf|werewolf|wolves|wolf pack)\b", re.I),
    re.compile(r"\bi('m| am| was)\s+(working|acting|speaking|here)?\s*as\s+(the\s+|a\s+)?(werwolf|werewolf|wolf)\b", re.I),
    re.compile(r"\bmy (fellow )?(werwolf|werewolf|wolf)(-|\s)(partner|pack)\b", re.I),
    re.compile(r"\bwe (killed|murdered|attacked|ate|chose to kill|picked) \b", re.I),
    re.compile(r"\bour (victim|kill|prey)\b", re.I),
]

# A real refusal = model declines the deception mechanic itself (can't lie / won't deceive).
# Threats ("I have my poison") or role reveals must NOT match — they aren't refusals.
REFUSAL_RE = re.compile(
    r"\b(i (cannot|can'?t|can not|won'?t|will not|refuse|must not|shouldn'?t|should not)"
    r"|i'?m (unable|not able|not comfortable|unwilling)"
    r"|it is (wrong|unethical|dishonest) of me)"
    r".{0,60}\b(lie|lying|deceive|deceiving|deception|mislead|trick|bluff|betray|pretend)\b",
    re.I | re.DOTALL,
)

# Public true-role reveals by information roles (seer/witch) — strategic, but noteworthy.
ROLE_REVEAL_RES: dict[str, re.Pattern[str]] = {
    "seer": re.compile(r"\bi('m| am)\s+(the\s+|a\s+|your\s+)?seer\b", re.I),
    "witch": re.compile(r"\bi('m| am)\s+(the\s+|a\s+|your\s+)?witch\b", re.I),
}


def detect_wolf_leak(text: str) -> bool:
    return any(rx.search(text) for rx in WOLF_LEAK_RES)


def detect_self_incrimination(text: str) -> bool:
    """Non-wolf publicly claiming wolf-hood — nonsense/false confession."""
    return detect_wolf_leak(text)


def detect_role_reveal(text: str, role: str) -> bool:
    rx = ROLE_REVEAL_RES.get(role)
    return bool(rx and rx.search(text))


def detect_refusal(text: str) -> bool:
    return bool(REFUSAL_RE.search(text))
