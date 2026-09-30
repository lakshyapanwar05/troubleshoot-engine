"""Text generation rules — goal, title, actionName, description.

All generated strings are enforced by word-count and casing rules.
No LLM is used; everything comes from templates and lexicons.
"""
from __future__ import annotations

import re
from typing import Optional

import yaml

from app.config import (
    DESC_WORDS,
    TITLE_WORDS,
    GOAL_TROUBLESHOOTING,
    GOAL_CONFIGURATION,
    RULES_DIR,
)


# ── Load symptom rules once ───────────────────────────────────────────
_symptoms_data: Optional[dict] = None


def _load_symptoms() -> dict:
    global _symptoms_data
    if _symptoms_data is None:
        with open(RULES_DIR / "symptoms.yaml", "r", encoding="utf-8") as f:
            _symptoms_data = yaml.safe_load(f)
    return _symptoms_data


# ── Word-count enforcement ────────────────────────────────────────────

def enforce_word_range(
    text: str,
    min_words: int,
    max_words: int,
    pad_word: str = "settings",
) -> str:
    """Enforce a word count range on text.

    If too long, truncate to max_words (ending with a period if original did).
    If too short, pad with pad_word repetitions.
    """
    words = text.split()
    had_period = text.rstrip().endswith(".")

    if len(words) > max_words:
        words = words[:max_words]
        result = " ".join(words)
        # Remove trailing punctuation before adding period
        result = result.rstrip(".,;:!? ")
        if had_period:
            result += "."
        return result

    # Too short — shouldn't normally happen with good templates
    while len(words) < min_words:
        words.append(pad_word)

    result = " ".join(words)
    if had_period and not result.endswith("."):
        result += "."
    return result


def enforce_description(desc: str) -> str:
    """Enforce description rules: starts with 'It will', 5-7 words."""
    if not desc.startswith("It will"):
        desc = "It will " + desc.lstrip("It will ").strip()

    # Remove trailing period for word counting, re-add after
    clean = desc.rstrip(".")
    words = clean.split()
    min_w, max_w = DESC_WORDS

    if len(words) > max_w:
        words = words[:max_w]
        desc = " ".join(words).rstrip(".,;:!? ") + "."
    elif len(words) < min_w:
        # Pad to minimum
        while len(words) < min_w:
            words.append("properly")
        desc = " ".join(words).rstrip(".,;:!? ") + "."
    else:
        desc = " ".join(words).rstrip(".,;:!? ") + "."

    return desc


# ── Symptom matching ──────────────────────────────────────────────────

def match_symptom(query: str) -> dict:
    """Match query text against symptom keyword lists.

    Returns dict with: topic, title, goal_type.
    Falls back to a generic if nothing matches.
    """
    data = _load_symptoms()
    q_lower = query.lower()

    for entry in data.get("symptoms", []):
        for kw in entry["keywords"]:
            if kw.lower() in q_lower:
                return {
                    "topic": entry["topic"],
                    "title": entry["title"],
                    "goal_type": entry["goal_type"],
                }

    fallback = data.get("fallback", {})
    return {
        "topic": fallback.get("topic", "Screen"),
        "title": fallback.get("title", "Screen display issue"),
        "goal_type": fallback.get("goal_type", "troubleshooting"),
    }


def extract_salient_symptoms(query: str) -> list[str]:
    """Extract salient symptom terms from query, ignoring generic devices and fillers."""
    q = query.lower()
    symptoms = []

    phrases = [
        # Blank / black / power / startup
        "blank", "black", "white", "blue", "tiny text",
        "turn on", "turn it on", "turning on", "power on", "powers on", "power button", "start up",
        # Damage
        "crack", "cracked", "shatter", "broken", "physical damage", "liquid",
        # Touch
        "touch", "lag", "laggy", "delayed", "delay", "unresponsive", "sensitivity",
        # Flicker
        "flicker", "flickers", "flashing", "flash",
        # Distortion
        "distort", "distorted", "garbled", "glitch",
        # Rotation
        "rotate", "rotation", "orientation", "portrait", "landscape",
        # Screen size
        "small screen", "doesn't fill", "won't expand",
        # Floating
        "floating circle", "circle", "hover", "hovers", "assistant menu",
        # Data transfer
        "data transfer", "transfer data", "qr code", "scan",
        # Email
        "email", "gmail",
        # Charging
        "charger", "charging", "plug in",
        # Darkness
        "dark", "won't open", "nothing loads",
        # Fold
        "inner screen", "cover screen", "folds",
        # Activation
        "activation", "carrier", "deactivated",
    ]
    for p in phrases:
        if p in q:
            symptoms.append(p)

    return symptoms


_synonym_word_to_group: Optional[dict[str, set[str]]] = None


def _load_synonym_groups() -> dict[str, set[str]]:
    """Build synonym equivalence groups from rules/synonyms.yaml."""
    global _synonym_word_to_group
    if _synonym_word_to_group is not None:
        return _synonym_word_to_group

    groups: list[set[str]] = [
        {"blank", "black", "dark", "empty"},
        {"flash", "flashes", "flashing", "flicker", "flickers", "blink", "strobe"},
        {"crack", "cracked", "broken", "shatter", "shattered", "smashed", "damaged"},
        {"slow", "lag", "laggy", "delay", "delayed", "unresponsive", "sluggish", "latency"},
        {"email", "mail", "gmail"},
        {"data transfer", "transfer data", "migrate", "copy data"},
        {"distort", "distorted", "garbled", "glitch", "glitchy", "corrupted", "messed up"},
        {"freeze", "frozen", "stuck", "hung", "not responding", "locked up"},
        {"turn on", "turning on", "power on", "powers on", "start up", "boot up", "switch on"},
        {"charger", "charging", "charge", "plug in", "power up"},
        {"rotate", "rotation", "orientation", "landscape", "portrait"},
    ]

    syn_path = RULES_DIR / "synonyms.yaml"
    if syn_path.exists():
        with open(syn_path, "r", encoding="utf-8") as f:
            raw_syns = yaml.safe_load(f) or {}
        excluded = {"screen", "phone", "tablet", "settings", "touch"}
        for k, v in raw_syns.items():
            if k not in excluded and isinstance(v, list):
                grp = {k.lower()} | {str(x).lower() for x in v}
                merged = False
                for existing in groups:
                    if existing & grp:
                        existing.update(grp)
                        merged = True
                        break
                if not merged:
                    groups.append(grp)

    mapping: dict[str, set[str]] = {}
    for g in groups:
        for word in g:
            if word not in mapping:
                mapping[word] = set()
            mapping[word].update(g)

    _synonym_word_to_group = mapping
    return _synonym_word_to_group


def _expand_symptom_candidates(symptom: str) -> set[str]:
    """Expand a salient symptom term to its synonyms."""
    s = symptom.lower().strip()
    candidates = {s}
    mapping = _load_synonym_groups()
    if s in mapping:
        candidates.update(mapping[s])
    s_stem = s.rstrip("sedingy")
    if len(s_stem) >= 4:
        for w, grp in mapping.items():
            if w.startswith(s_stem) or s_stem.startswith(w.rstrip("sedingy")):
                candidates.update(grp)
    return candidates


def section_has_symptom(heading: str, body: str, symptoms: list[str]) -> bool:
    """Verify that at least one salient symptom appears in the section."""
    if not symptoms:
        return False
    text = (heading + " " + body).lower()

    for s in symptoms:
        candidates = _expand_symptom_candidates(s)
        for cand in candidates:
            if re.search(r"\b" + re.escape(cand) + r"\b", text):
                return True
            if len(cand) > 4:
                root = cand.rstrip("sedingy")
                if len(root) >= 4 and re.search(r"\b" + re.escape(root), text):
                    return True
    return False


# ── Goal generation ──────────────────────────────────────────────────

def generate_goal(topic: str, goal_type: str = "troubleshooting") -> str:
    """Generate the goal string from topic.

    topic must be Title Case.
    """
    # Ensure topic is Title Case
    topic = to_title_case(topic)
    if goal_type == "configuration":
        return GOAL_CONFIGURATION.format(topic=topic)
    return GOAL_TROUBLESHOOTING.format(topic=topic)


# ── Title generation ──────────────────────────────────────────────────

def generate_title(symptom_title: str) -> str:
    """Generate a 2-3 word sentence-case title.

    Input: symptom_title from the symptom rules.
    Output: sentence case, 2-3 words.
    """
    title = to_sentence_case(symptom_title)
    words = title.split()
    min_w, max_w = TITLE_WORDS
    if len(words) > max_w:
        words = words[:max_w]
    elif len(words) < min_w:
        words.append("issue")
    return " ".join(words)


# ── Action name generation ───────────────────────────────────────────

def generate_action_name(section_heading: str, steps: list[str]) -> str:
    """Generate a Title Case action name from section heading or step content.

    The name should represent ONE physical screen or feature.
    """
    # If the heading mentions both Cache and Data, differentiate by steps
    if section_heading and ("cache and data" in section_heading.lower() or "cache & data" in section_heading.lower()):
        steps_text = " ".join(steps).lower()
        if "clear data" in steps_text:
            return "Clear Email App Data"
        if "clear cache" in steps_text:
            return "Clear Email App Cache"

    GENERIC_HEADINGS = {
        "introduction",
        "overview",
        "summary",
        "general",
        "main",
        "preamble",
        "details",
        "steps",
        "troubleshooting",
        "some things to check first",
    }

    # Try to use the section heading first if not generic
    if section_heading:
        name = _clean_action_name(section_heading)
        if name and name.lower() not in GENERIC_HEADINGS:
            return to_title_case(name)

    # Fall back to step content
    if steps:
        steps_text = " ".join(steps).lower()
        if "mouse" in steps_text or "keyboard" in steps_text:
            return "Access Phone Using Mouse"
        # Extract the key noun phrase from the first meaningful step
        first = steps[0] if steps else ""
        name = _extract_action_from_step(first)
        if name and name.lower() not in GENERIC_HEADINGS:
            return to_title_case(name)

    return "General Settings"


def _clean_action_name(heading: str) -> str:
    """Clean a section heading into an action name."""
    # Remove step numbers, markdown, etc.
    heading = re.sub(r"^#+\s*", "", heading)
    heading = re.sub(r"^(?:Step\s+)?\d+[.:)]\s*", "", heading, flags=re.IGNORECASE)
    heading = heading.strip()

    # Truncate to reasonable length (max 7 words for action name)
    words = heading.split()
    if len(words) > 7:
        words = words[:7]
    name = " ".join(words)
    # Strip trailing conjunctions, prepositions, articles, or punctuation
    while True:
        new_name = re.sub(r"\s+(?:and|or|to|then|for|with|of|in|on|at|by|the|a|an|but)$", "", name, flags=re.IGNORECASE)
        if new_name == name:
            break
        name = new_name
    name = name.rstrip(".,;:!? ")
    return name


def _extract_action_from_step(step: str) -> str:
    """Extract a short action name from a step string."""
    # "Navigate to and open Settings." -> "Open Settings"
    # "Tap on Display." -> "Display Settings"
    step = step.rstrip(".")
    m = re.match(r"(?:Navigate to and open|Go to|Open)\s+(.+)", step, re.IGNORECASE)
    if m:
        return m.group(1).strip() + " Settings"

    m = re.match(r"(?:Tap|Tap on|Select|Touch)\s+(.+)", step, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return step[:30]


# ── Description generation from templates ────────────────────────────

def get_description_template(action_key: str) -> str:
    """Get a description template by action key.

    Applies the word-count enforcer to the result.
    """
    data = _load_symptoms()
    templates = data.get("description_templates", {})

    template = templates.get(action_key, {}).get("template")
    if template:
        return enforce_description(template)

    # Generic fallback
    return enforce_description("It will open the relevant screen.")


def generate_description_for_steps(
    steps: list[str],
    category: str,
    section_heading: str = "",
) -> str:
    """Generate a description based on step content and category.

    Uses keyword matching against the description_templates.
    """
    all_text = " ".join(steps).lower() + " " + section_heading.lower()

    # Match against known action keys
    key_patterns = [
        ("factory_reset", ["factory data reset", "factory reset", "delete all"]),
        ("safe_mode", ["safe mode"]),
        ("clear_data", ["clear data", "clear the app's data"]),
        ("clear_cache", ["clear cache", "clear the cache"]),
        ("force_restart", ["force restart", "force a restart", "press and hold both"]),
        ("restart", ["restart your", "reboot"]),
        ("check_damage", ["physical damage", "liquid exposure", "inspect", "check for"]),
        ("charge", ["charge", "charger", "charging"]),
        ("power_on", ["power on", "turn it on", "attempt to power"]),
        ("update_software", ["software update", "update", "keeping.*updated"]),
        ("contact_support", ["contact customer", "contact support", "further assistance"]),
        ("visit_service", ["service center", "walk-in", "mail-in", "schedule a repair"]),
        ("backup", ["back up", "backup"]),
        ("touch_sensitivity", ["touch sensitivity"]),
        ("display_settings", ["display", "screen orientation", "auto rotate"]),
        ("navigation_bar", ["navigation bar"]),
        ("connections", ["connections", "wi-fi", "wifi"]),
        ("data_transfer", ["data transfer"]),
        ("repair_service", ["repair", "authorized repair"]),
        ("remove_account", ["remove.*account", "re-add"]),
        ("app_management", ["apps", "app", "storage", "cache"]),
    ]

    for key, patterns in key_patterns:
        for pat in patterns:
            if re.search(pat, all_text, re.IGNORECASE):
                return get_description_template(key)

    # Category-based fallback
    if category == "manual":
        return get_description_template("check_damage")
    if category == "critical":
        return get_description_template("restart")

    return get_description_template("general")


# ── Casing utilities ──────────────────────────────────────────────────

def to_title_case(text: str) -> str:
    """Convert text to Title Case, preserving known acronyms."""
    # Simple title case with some exceptions
    words = text.split()
    result = []
    small_words = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
    for i, w in enumerate(words):
        if w.upper() in {"USB", "LDI", "QR", "PIN", "HDMI", "SIM", "PC", "TV", "LED", "UI"}:
            result.append(w.upper())
        elif i == 0 or w.lower() not in small_words:
            result.append(w.capitalize())
        else:
            result.append(w.lower())
    return " ".join(result)


def to_sentence_case(text: str) -> str:
    """Convert text to sentence case: first word capitalized, rest lower."""
    if not text:
        return text
    words = text.split()
    if not words:
        return text
    # Keep first word capitalized, rest lower (except acronyms)
    result = [words[0].capitalize()]
    for w in words[1:]:
        if w.upper() in {"USB", "LDI", "QR", "PIN", "HDMI", "SIM", "PC", "TV", "LED", "UI"}:
            result.append(w.upper())
        else:
            result.append(w.lower())
    return " ".join(result)
