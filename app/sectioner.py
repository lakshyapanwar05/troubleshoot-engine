"""SIIS text -> preamble-stripped sections.

Splits raw SIIS content into discrete sections based on markdown headings
and 'Step N' patterns, then drops non-actionable narrative.
"""
from __future__ import annotations

import re
from typing import List, Tuple


def strip_preamble(content: str) -> str:
    """Strip the category preamble up to the first '): '.

    Example preamble:
      Smartphone,Others Mobile,Tablet Blank or black display ( Smartphone,...):
    """
    # Find the pattern 'categories): ' at the start
    m = re.search(r"\)\s*:\s*", content)
    if m:
        content = content[m.end():]
    return content.strip()


def split_into_sections(content: str) -> List[Tuple[str, str]]:
    """Split content into (heading, body) sections.

    Splits on:
    - Markdown headings (# ## ###)
    - 'Step N:' or '## Step N:' patterns
    - Numbered sections '### 1.' etc.

    Returns list of (heading, body_text) tuples.
    """
    # Strip preamble first
    content = strip_preamble(content)

    # Split on heading patterns
    # Captures: ## Heading, ### Heading, # Heading, ## Step N: Heading
    heading_pattern = re.compile(
        r"((?:^|\n)\s*#{1,3}\s*.+?)(?=\n|$)"
    )

    sections: List[Tuple[str, str]] = []
    # Find all headings and their positions
    headings = list(heading_pattern.finditer(content))

    if not headings:
        # No headings found — treat entire content as one section
        return [("Main", content.strip())]

    # Add content before first heading as intro section
    first_start = headings[0].start()
    if first_start > 0:
        intro = content[:first_start].strip()
        if intro:
            sections.append(("Introduction", intro))

    # Process each heading and its body
    for i, match in enumerate(headings):
        heading_text = match.group().strip().lstrip("#").strip()

        # Body is from end of this heading to start of next heading
        body_start = match.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
        body = content[body_start:body_end].strip()

        if heading_text or body:
            sections.append((heading_text, body))

    return sections


def is_actionable_section(heading: str, body: str) -> bool:
    """Check if a section contains actionable troubleshooting steps.

    Drops sections that are:
    - Pure narrative without instructions
    - About other brands (iPhone, AirPlay)
    - Glossary/definition sections
    - "at the provided links" type redirections
    """
    combined = (heading + " " + body).lower()

    # Non-actionable patterns
    non_actionable = [
        "glossary",
        "useful app pairing ideas",
        "tips for mirroring",
        "understanding screen damage",
        "understanding video flickering",
        "what is screen mirroring",
        "what is casting",
        "screen mirroring vs",
    ]
    for pattern in non_actionable:
        if pattern in combined:
            return False

    # Skip sections about other brands
    other_brand_patterns = [
        r"\bairplay\b",
        r"\biphone\b",
        r"\bipad\b",
        r"\bapple\b",
        r"\bwindows\s+\d+\b",
        r"\bpc\b.*\bto\s+a\s+tv\b",
    ]
    for pat in other_brand_patterns:
        if re.search(pat, combined):
            return False

    # Skip "at the provided links" type redirections
    if "at the provided links" in combined:
        return False

    # Must have at least some verb-like content to be actionable
    action_indicators = [
        "navigate", "go to", "open", "tap", "press", "swipe",
        "select", "toggle", "turn", "enable", "disable", "restart",
        "clear", "check", "inspect", "contact", "visit", "connect",
        "charge", "insert", "remove", "hold", "force",
    ]
    has_action = any(ind in combined for ind in action_indicators)

    return has_action


def get_actionable_sections(content: str) -> List[Tuple[str, str]]:
    """Get only the actionable sections from SIIS content.

    Full pipeline: strip preamble -> split -> filter.
    """
    sections = split_into_sections(content)
    return [
        (heading, body)
        for heading, body in sections
        if is_actionable_section(heading, body)
    ]
