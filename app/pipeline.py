"""Pipeline orchestrator — ties all modules together.

Entry point: process_query(query, siis_response) -> envelope dict.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional, Union

from app.config import (
    MAX_ACTIONS_PER_GOAL,
    MAX_GOALS,
    REL_THRESHOLD,
)
from app.normalize import normalize_query, canonicalize_query
from app.sectioner import get_actionable_sections, split_into_sections, strip_preamble
from app.steps import extract_step_chains
from app.classify import classify_action
from app.ordering import order_actions
from app.textrules import (
    match_symptom,
    generate_goal,
    generate_title,
    generate_action_name,
    generate_description_for_steps,
    extract_salient_symptoms,
    section_has_symptom,
)
from app.deeplinks import match_deeplink
from app.retrieval import CatalogRetriever, score_sections
from app.validators import final_gate
from app.variations import generate_variations
from app.cache import SemanticCache
from app.loader import (
    load_deeplinks,
    load_deeplinks_full,
    build_catalog_uri_set,
    build_catalog_text_index,
)
from app.envelope import SIISObject

logger = logging.getLogger(__name__)


class TroubleshootPipeline:
    """The main troubleshooting pipeline.

    Loads catalog and model once, then processes queries.
    """

    def __init__(self):
        self.catalog_retriever: Optional[CatalogRetriever] = None
        self.catalog_uris: set[str] = set()
        self.cache = SemanticCache()
        self.local_sections: list[tuple[str, str, str, str]] = []
        self.local_section_embeddings: Optional[Any] = None
        self._initialized = False

    def initialize(self) -> None:
        """Load catalog, build indices, load cache. Call once at startup."""
        if self._initialized:
            return

        logger.info("Initializing pipeline...")

        # Load catalog
        all_deeplinks = load_deeplinks_full()
        self.catalog_uris = build_catalog_uri_set(all_deeplinks)

        actionable_deeplinks = load_deeplinks()
        catalog_pairs = build_catalog_text_index(actionable_deeplinks)
        catalog_texts = [text for text, _ in catalog_pairs]
        catalog_entries = [entry for _, entry in catalog_pairs]

        self.catalog_retriever = CatalogRetriever(catalog_texts, catalog_entries)

        # Index local SIIS sections for fallback search
        from app.loader import load_siis_responses
        siis_rows = load_siis_responses()
        self.local_sections = []
        section_texts = []
        seen_titles = set()
        for r in siis_rows:
            title = r["siis_response"]["title"]
            content = r["siis_response"]["content"]
            if title in seen_titles:
                continue
            seen_titles.add(title)
            actionable = get_actionable_sections(content)
            for h, b in actionable:
                self.local_sections.append((title, content, h, b))
                section_texts.append(f"{title} {h} {b}".strip())

        from app.retrieval import encode_texts, encode_single, get_model
        if section_texts:
            self.local_section_embeddings = encode_texts(section_texts)

        # Load cache
        self.cache.load()

        # Preload and warm up embedding model
        get_model()
        encode_single("startup warmup")

        self._initialized = True
        logger.info("Pipeline initialized: %d catalog entries, %d cache entries, %d local sections",
                     len(catalog_texts), self.cache.size, len(self.local_sections))

    def process_query(
        self,
        raw_query: str,
        siis_response: Optional[Union[str, SIISObject, dict]] = None,
    ) -> dict:
        """Process a single query through the full pipeline.

        Returns an envelope dict ready for the API.
        """
        self.initialize()
        start_time = time.time()

        # Normalize and parse SIIS
        norm = normalize_query(raw_query)
        canonical = norm["canonical_queries"][0] if norm["canonical_queries"] else raw_query

        # Parse SIIS response
        siis_title, siis_content = self._parse_siis(siis_response)

        # If no SIIS provided, check cache first, then fall back to local SIIS search
        if siis_content is None:
            cached = self.cache.get(canonical)
            latency = int((time.time() - start_time) * 1000)
            if cached:
                fallback = "no_match" if not cached.get("contexts") else None
                return self._build_envelope(
                    canonical, cached, latency, cache_hit=True, fallback=fallback
                )

            # Cache miss with no SIIS: search sections of local SIIS articles
            found_goal = None
            if self.local_section_embeddings is not None and len(self.local_section_embeddings) > 0:
                import numpy as np
                from app.retrieval import encode_single
                query_emb = encode_single(canonical)
                sims = self.local_section_embeddings @ query_emb
                sorted_indices = np.argsort(sims)[::-1]
                salient_terms = extract_salient_symptoms(canonical)

                for idx in sorted_indices[:15]:
                    score = float(sims[idx])
                    if score < REL_THRESHOLD:
                        break
                    title, content, h, b = self.local_sections[idx]
                    if section_has_symptom(h, b, salient_terms):
                        raw_sub = norm["sub_queries"][0] if norm["sub_queries"] else canonical
                        sub_canonical = norm["canonical_queries"][0] if norm["canonical_queries"] else canonical
                        goal = self._process_single(sub_canonical, raw_sub, title, content)
                        if goal:
                            found_goal = goal
                            break

            if found_goal:
                result = {"contexts": [found_goal]}
                variations = generate_variations(canonical)
                self.cache.put(canonical, result, variations)
                latency = int((time.time() - start_time) * 1000)
                return self._build_envelope(
                    canonical, result, latency,
                    cache_hit=False, variations=variations,
                )

            return self._build_envelope(
                canonical, {"contexts": []}, latency,
                cache_hit=False, fallback="no_siis_context",
            )

        # Check cache first
        cached = self.cache.get(canonical)
        if cached:
            latency = int((time.time() - start_time) * 1000)
            fallback = "no_match" if not cached.get("contexts") else None
            return self._build_envelope(
                canonical, cached, latency, cache_hit=True, fallback=fallback
            )

        # Process each sub-query
        all_goals = []
        for i, sub_query in enumerate(norm["sub_queries"]):
            sub_canonical = norm["canonical_queries"][i]
            goal = self._process_single(sub_canonical, sub_query, siis_title, siis_content)
            if goal:
                all_goals.append(goal)

        # Sort goals by score descending
        all_goals.sort(key=lambda g: g.get("score", 0), reverse=True)
        all_goals = all_goals[:MAX_GOALS]

        result = {"contexts": all_goals}

        # Generate variations and cache
        variations = generate_variations(canonical)

        # Cache the result
        self.cache.put(canonical, result, variations)

        latency = int((time.time() - start_time) * 1000)

        if not all_goals:
            return self._build_envelope(
                canonical, result, latency,
                cache_hit=False, fallback="no_match",
                variations=variations,
            )

        return self._build_envelope(
            canonical, result, latency,
            cache_hit=False, variations=variations,
        )

    def _process_single(
        self,
        canonical: str,
        raw_sub: str,
        siis_title: str,
        siis_content: str,
    ) -> Optional[dict]:
        """Process a single sub-query against the SIIS content.

        Returns a Goal dict or None if no relevant content.
        """
        # Section the SIIS content
        all_sections = get_actionable_sections(siis_content)

        if not all_sections:
            logger.info("No actionable sections found for: %s", canonical[:60])
            return None

        # Score sections for relevance
        scored_sections = score_sections(canonical, all_sections)

        # Log best section score
        if scored_sections:
            best_section, best_score = scored_sections[0]
            logger.info(
                "Best section score for '%s': %.3f ('%s')",
                canonical[:40], best_score, best_section[0][:40],
            )

        # Extract salient symptom terms from query
        salient_symptoms = extract_salient_symptoms(canonical + " " + raw_sub)

        # Relevance gate: keep only sections above threshold AND matching salient symptoms
        relevant_sections = [
            (section, score) for section, score in scored_sections
            if score >= REL_THRESHOLD and section_has_symptom(section[0], section[1], salient_symptoms)
        ]

        if not relevant_sections:
            logger.info(
                "No sections passed relevance gate (REL_THRESHOLD=%.2f, symptoms=%s) for: %s",
                REL_THRESHOLD, salient_symptoms, canonical[:60],
            )
            return None

        # Extract step chains from relevant sections
        all_chains = []
        for (heading, body), score in relevant_sections:
            chains = extract_step_chains(heading, body)
            for chain in chains:
                chain["relevance_score"] = score
            all_chains.extend(chains)

        if not all_chains:
            logger.info("No step chains extracted for: %s", canonical[:60])
            return None

        # Match symptoms for metadata
        symptom = match_symptom(canonical + " " + raw_sub)

        # Build actions from chains, unifying duplicates by actionName
        actions = []
        action_by_name: dict[str, dict] = {}

        for chain in all_chains:
            steps = chain["steps"]
            heading = chain["heading"]

            # Classify
            category = classify_action(steps, heading)

            # Generate text fields
            action_name = generate_action_name(heading, steps)
            description = generate_description_for_steps(steps, category, heading)

            # Match deeplink
            actionable_dl, validation_dl = match_deeplink(
                steps, action_name, heading, category,
                self.catalog_retriever, self.catalog_uris,
            )

            # Build step group
            step_group = {
                "steps": steps,
                "actionableDeeplink": actionable_dl,
                "validationDeeplink": validation_dl,
            }

            if action_name in action_by_name:
                existing = action_by_name[action_name]
                # Check if this exact step chain already exists in this action
                is_dup = any(sg["steps"] == steps for sg in existing["stepGroups"])
                if not is_dup:
                    existing["stepGroups"].append(step_group)
            else:
                action = {
                    "actionName": action_name,
                    "description": description,
                    "stepGroups": [step_group],
                    "category": category,
                }
                action_by_name[action_name] = action
                actions.append(action)

        actions = actions[:MAX_ACTIONS_PER_GOAL]

        if not actions:
            return None

        # Order actions
        actions = order_actions(actions)

        # Compute overall score from relevance scores
        avg_score = sum(c.get("relevance_score", 0) for c in all_chains) / len(all_chains)
        score = round(min(max(avg_score, 0.0), 1.0), 2)

        # Build goal
        goal = generate_goal(symptom["topic"], symptom["goal_type"])
        title = generate_title(symptom["title"])

        goal_dict = {
            "goal": goal,
            "title": title,
            "score": score,
            "actions": actions,
        }

        return goal_dict

    def _parse_siis(
        self,
        siis_response: Optional[Union[str, SIISObject, dict]],
    ) -> tuple[str, Optional[str]]:
        """Parse the SIIS response into (title, content).

        Returns (title, None) if no content available.
        """
        if siis_response is None:
            return "", None

        if isinstance(siis_response, str):
            if not siis_response.strip():
                return "", None
            return "", siis_response

        if isinstance(siis_response, SIISObject):
            return siis_response.title, siis_response.content

        if isinstance(siis_response, dict):
            return siis_response.get("title", ""), siis_response.get("content")

        return "", None

    def _build_envelope(
        self,
        canonical: str,
        response: dict,
        latency_ms: int,
        cache_hit: bool = False,
        fallback: Optional[str] = None,
        variations: Optional[list[str]] = None,
    ) -> dict:
        """Build the full response envelope."""
        # Apply final gate
        envelope = {
            "query": canonical,
            "query_variations": variations or [],
            "response": response,
            "meta": {
                "latency_ms": latency_ms,
                "cache_hit": cache_hit,
                "model": "rules-v1",
                "cost_usd": 0.0,
            },
        }

        if fallback:
            envelope["meta"]["fallback"] = fallback

        # Run final gate validation
        envelope = final_gate(envelope, self.catalog_uris)

        return envelope

    def prewarm(self, rows: list[dict]) -> None:
        """Prewarm the cache with all provided rows.

        Each row is {original_query, siis_response: {title, content}}.
        """
        self.initialize()
        self.cache.clear()
        logger.info("Prewarming cache with %d rows...", len(rows))

        for i, row in enumerate(rows):
            query = row.get("original_query", "")
            siis = row.get("siis_response")
            try:
                result = self.process_query(query, siis)
                logger.info(
                    "Prewarm [%d/%d] query='%s' goals=%d cache_hit=%s",
                    i + 1, len(rows), query[:40],
                    len(result.get("response", {}).get("contexts", [])),
                    result.get("meta", {}).get("cache_hit"),
                )
            except Exception as e:
                logger.error("Prewarm failed for row %d: %s", i, e)

        # Save cache
        self.cache.save()
        logger.info("Prewarm complete. Cache size: %d", self.cache.size)


# Singleton pipeline instance
_pipeline: Optional[TroubleshootPipeline] = None


def get_pipeline() -> TroubleshootPipeline:
    """Get or create the singleton pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = TroubleshootPipeline()
    return _pipeline
