"""Request/response envelope models — wraps schema.py for the API layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, field_validator

from schema import ContextDeeplinkResponse


# ── Request ────────────────────────────────────────────────────────────

class SIISObject(BaseModel):
    """Structured SIIS response with title + content."""
    title: str
    content: str


class TroubleshootRequest(BaseModel):
    """POST /v1/troubleshoot body.

    siis_response can be:
      - a plain string (raw text)
      - an object {title, content}
      - null / omitted  (cache-only lookup)
    """
    query: str
    siis_response: Optional[Union[str, SIISObject]] = None

    @field_validator("siis_response", mode="before")
    @classmethod
    def coerce_siis(cls, v: Any) -> Optional[Union[str, SIISObject]]:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            # Accept dict form and coerce to SIISObject
            return SIISObject(**v)
        return v


# ── Response ───────────────────────────────────────────────────────────

class MetaInfo(BaseModel):
    """Metadata about the response."""
    latency_ms: int = 0
    cache_hit: bool = False
    model: str = "rules-v1"
    cost_usd: float = 0.0
    fallback: Optional[str] = None  # "no_match" | "no_siis_context" | None


class TroubleshootResponse(BaseModel):
    """Full API response envelope."""
    query: str
    query_variations: List[str] = []
    response: ContextDeeplinkResponse
    meta: MetaInfo = MetaInfo()
