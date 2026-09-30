"""Rule-based atomic step extraction and screen-chain grouping.

This is the core module: extracts actionable steps from SIIS section text,
splits compound sentences into atomic steps, groups them into screen chains,
and assigns each chain as one action (one physical screen = one stepGroup).
"""
from __future__ import annotations

import re
from typing import List, Tuple, Optional

import yaml

from app.config import RULES_DIR, MAX_ACTIONS_PER_GOAL
from app.validators import scrub_urls


# ── Load verb lexicon ─────────────────────────────────────────────────
_verbs_data: Optional[dict] = None


def _load_verbs() -> dict:
    global _verbs_data
    if _verbs_data is None:
        with open(RULES_DIR / "verbs.yaml", "r", encoding="utf-8") as f:
            _verbs_data = yaml.safe_load(f)
    return _verbs_data


def _get_all_verbs() -> list[str]:
    """Get a flat list of all verbs, sorted longest-first for greedy matching."""
    data = _load_verbs()
    verbs = []
    for category_verbs in data.values():
        if isinstance(category_verbs, list):
            verbs.extend(category_verbs)
    # Sort longest-first so "press and hold" matches before "press"
    return sorted(verbs, key=len, reverse=True)


# ── Step extraction ──────────────────────────────────────────────────

def is_instruction_line(line: str) -> bool:
    """Check if a line/sentence is an instruction.

    True if it starts with a known verb or contains a Settings > A > B chain.
    """
    line_lower = line.strip().lower()
    if not line_lower:
        return False

    # Check for Settings chain: Settings > A > B
    if re.search(r"settings\s*>\s*\w", line_lower):
        return True

    # Check if starts with a known verb
    for verb in _get_all_verbs():
        if line_lower.startswith(verb.lower()):
            return True

    return False


def extract_instructions(body: str) -> list[str]:
    """Extract instruction lines from a section body.

    Lines that start with verbs or contain settings chains are instructions.
    Also handles 'You can verb...' patterns and mid-sentence verbs.
    Non-instruction lines (narrative) are dropped.
    """
    # Split on newlines and sentence boundaries within lines
    raw_lines = body.split("\n")
    instructions = []
    all_verbs = _get_all_verbs()

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue

        # Try splitting on sentence boundaries for lines with multiple sentences
        sentences = _split_sentences(line)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            # Strip conditional/device prefixes like:
            # "For devices with a Power button: "
            # "On devices with a Side button: "
            # "To resolve this issue, please try the following steps: "
            clean_sent = re.sub(
                r"^(?:(?:For|On)\s+devices\s+with\s+[^:]*:|If\s+(?:your\s+)?device\s+[^:]*:|To\s+[^:]*:\s*|Please\s+note\s+that\s+[^:]*:)\s*",
                "", sent, flags=re.IGNORECASE,
            ).strip()

            target_sent = clean_sent if clean_sent else sent

            if is_instruction_line(target_sent):
                instructions.append(target_sent[0].upper() + target_sent[1:])
                continue

            # Handle "You can verb..." patterns -> extract "Verb..."
            you_can = re.match(
                r"^(?:You\s+can|You\s+may|You\s+should|Please)\s+(.+)$",
                target_sent, re.IGNORECASE,
            )
            if you_can:
                rest = you_can.group(1).strip()
                if is_instruction_line(rest):
                    # Capitalize the verb
                    instructions.append(rest[0].upper() + rest[1:])
                    continue

            # Handle mid-sentence verbs: "..., visit/contact/schedule..."
            for verb in ["visit", "contact", "schedule", "reach out"]:
                pat = re.compile(
                    r"(?:,\s*|\.\s*)" + re.escape(verb) + r"\s+",
                    re.IGNORECASE,
                )
                m = pat.search(target_sent)
                if m:
                    extracted = target_sent[m.start():].lstrip(",. ")
                    extracted = extracted[0].upper() + extracted[1:]
                    instructions.append(extracted)
                    break

    return instructions


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, being careful with abbreviations."""
    # Split on period followed by space and uppercase, or newline
    # But don't split on abbreviations like "e.g." or "i.e."
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return parts


def split_compound_step(step: str) -> list[str]:
    """Split a compound instruction into atomic steps.

    e.g., "Go to Settings, tap Connections, and then tap Wi-Fi."
    becomes ["Navigate to and open Settings.", "Tap on Connections.", "Tap on Wi-Fi."]
    """
    step = step.strip()
    if not step:
        return []

    # Handle "Alternatively, ..." prefix
    step = re.sub(r"^Alternatively,?\s*", "", step, flags=re.IGNORECASE)

    # Check for comma-separated chains with "and then"
    # Pattern: verb X, verb Y, and then verb Z
    chain_pattern = re.compile(
        r"(?:,\s*(?:and\s+)?then\s+|,\s+and\s+then\s+|,\s+then\s+)",
        re.IGNORECASE,
    )

    if chain_pattern.search(step):
        parts = chain_pattern.split(step)
        # Also split on remaining commas if parts start with verbs
        expanded = []
        for part in parts:
            part = part.strip().rstrip(".")
            # Further split on ", tap" or ", select" patterns
            sub_parts = re.split(r",\s+(?=(?:tap|select|touch|press|swipe|toggle|turn|enable|disable)\s)", part, flags=re.IGNORECASE)
            expanded.extend(sub_parts)
        return [res for p in expanded if (res := _format_atomic_step(p.strip()))]

    # Handle "verb X, verb Y" simple comma chains
    comma_chain = re.split(
        r",\s+(?=(?:tap|select|touch|press|swipe|toggle|turn|enable|disable|navigate|go\s+to|open)\s)",
        step,
        flags=re.IGNORECASE,
    )
    if len(comma_chain) > 1:
        return [res for p in comma_chain if (res := _format_atomic_step(p.strip()))]

    # Single step
    formatted = _format_atomic_step(step)
    return [formatted] if formatted else []


def is_vague_step(step: str) -> bool:
    """Check if a step is a non-actionable or vague filler instruction."""
    s = step.strip().rstrip(".").lower()
    if re.match(r"^(?:navigate|use)\s+(?:your\s+)?(?:device|phone|tablet)?\s*as\s+needed$", s):
        return True
    if re.match(r"^navigate\s+as\s+needed$", s):
        return True
    return False


def _format_atomic_step(step: str) -> str:
    """Format a single atomic step with proper style.

    - First step of settings chain: "Navigate to and open Settings."
    - Then: "Tap on <item>."
    - Ensure period ending
    - Scrub URLs
    """
    step = step.strip().rstrip(".")
    if is_vague_step(step):
        return ""
    step = scrub_urls(step)

    # Remove parenthetical brand names
    step = re.sub(r"\s*\([^)]*(?:TechCorp|Nexa|Samsung|Galaxy)[^)]*\)", "", step, flags=re.IGNORECASE)

    # Remove "click here" patterns
    step = re.sub(r"click\s+here", "", step, flags=re.IGNORECASE)

    # Remove trailing "at the provided links" etc.
    step = re.sub(r"\s*at the provided links.*$", "", step, flags=re.IGNORECASE)

    step = step.strip()

    # Normalize common step patterns
    # "Go to Settings" -> "Navigate to and open Settings."
    if re.match(r"^(?:go\s+to|navigate\s+to)\s+settings\b", step, re.IGNORECASE):
        step = "Navigate to and open Settings"

    # "Settings" alone -> "Navigate to and open Settings."
    if step.lower() == "settings":
        step = "Navigate to and open Settings"

    # Enforce word count limit (< 25 words)
    words = step.split()
    if len(words) >= 25:
        words = words[:24]
        step = " ".join(words).rstrip(".,;:!? ")

    # Capitalization: ensure first letter is capitalized
    if step:
        step = step[0].upper() + step[1:]

    # Ensure period
    if step and not step.endswith("."):
        step += "."

    return step


# ── Screen-chain grouping ────────────────────────────────────────────

def group_into_chains(instructions: list[str]) -> list[list[str]]:
    """Group instructions into screen chains.

    A chain starts at 'Settings' (Navigate to and open Settings.)
    and continues through taps until a toggle/select/value change.
    Physical steps group by proximity.

    Returns list of chains, each chain is a list of atomic steps.
    """
    chains: list[list[str]] = []
    current_chain: list[str] = []

    for instr in instructions:
        atoms = split_compound_step(instr)
        for atom in atoms:
            if not atom.strip():
                continue

            # Does this start a new settings chain?
            if _is_settings_start(atom):
                if current_chain:
                    chains.append(current_chain)
                current_chain = [atom]
            elif _is_new_action_start(atom) and current_chain:
                # New physical/manual action
                if not _is_continuation(atom, current_chain):
                    chains.append(current_chain)
                    current_chain = [atom]
                else:
                    current_chain.append(atom)
            else:
                current_chain.append(atom)

    if current_chain:
        chains.append(current_chain)

    return chains


def _is_settings_start(step: str) -> bool:
    """Check if this step starts a new settings chain."""
    return bool(re.match(
        r"^Navigate to and open Settings\.$",
        step,
        re.IGNORECASE,
    ))


def _is_new_action_start(step: str) -> bool:
    """Check if this step starts a fundamentally new action (not a tap continuation)."""
    # Physical actions that break a chain
    new_action_patterns = [
        r"^(?:press\s+and\s+hold|touch\s+and\s+hold)",
        r"^(?:connect|disconnect|plug|charge|insert|eject|remove)\b",
        r"^(?:contact|visit|call|reach\s+out|schedule)\b",
        r"^(?:inspect|examine|check\s+for\s+physical|shine)\b",
        r"^(?:restart|reboot)\b",
        r"^(?:force\s+(?:a\s+)?restart)\b",
        r"^(?:back\s+up|backup)\b",
    ]
    step_lower = step.lower().rstrip(".")
    return any(re.match(p, step_lower) for p in new_action_patterns)


def _is_continuation(step: str, chain: list[str]) -> bool:
    """Check if a step is a continuation of the current chain."""
    step_lower = step.lower()
    # Tap/Select/Toggle after a settings chain is a continuation
    if re.match(r"^(?:tap|select|toggle|touch|enable|disable|turn)", step_lower):
        return True
    return False


# ── Section-to-actions pipeline ──────────────────────────────────────

def extract_step_chains(
    heading: str,
    body: str,
) -> list[dict]:
    """Extract step chains from a single section.

    Returns list of dicts:
    {
        'heading': str,        # section heading
        'steps': [str, ...],   # atomic steps
        'raw_text': str,       # original body text for provenance
    }
    """
    instructions = extract_instructions(body)
    if not instructions:
        return []

    chains = group_into_chains(instructions)

    results = []
    for chain in chains:
        if chain:
            # Deduplicate near-identical steps
            deduped = _dedupe_steps(chain)
            if deduped:
                results.append({
                    "heading": heading,
                    "steps": deduped,
                    "raw_text": body,
                })

    return results


def _dedupe_steps(steps: list[str]) -> list[str]:
    """Remove near-identical duplicate steps (normalized string compare)."""
    seen: set[str] = set()
    result: list[str] = []
    for step in steps:
        normalized = _normalize_for_compare(step)
        if normalized not in seen:
            seen.add(normalized)
            result.append(step)
    return result


def _normalize_for_compare(step: str) -> str:
    """Normalize a step for comparison (lowercase, strip punctuation/whitespace)."""
    step = step.lower().strip()
    step = re.sub(r"[^\w\s]", "", step)
    step = re.sub(r"\s+", " ", step)
    return step
