"""
CampaignSegmentationPipeline
─────────────────────────────
LangGraph pipeline that scores and tiers a full contact list (5 000+) without
per-contact LLM calls.

DAG
───
  START
    │
  load_and_embed       asyncio.gather: Airtable table.all() + goal embedding
    │                  (two blocking I/O calls run concurrently)
  rag_score_all        single bulk pgvector cosine-similarity query
    │
  route_batches        conditional edge → list[Send]  (fan-out)
   ╱╲
  score_batch × N      pure-Python composite scoring — no I/O, no LLM
   ╲╱                  operator.add reducer merges all slices back
  finalize             sort within tiers → bulk DB insert → mark ready
    │
   END

Parallelism
───────────
At BATCH_SIZE=200 and 5 000 contacts → 25 concurrent score_batch nodes.
Each node is CPU-only (no I/O), so the gain is scheduling overhead removal
rather than wall-clock parallelism — but the pattern scales cleanly and
will matter if we add per-batch LLM enrichment in a future phase.

Streaming
─────────
Each major node emits events to the per-campaign asyncio.Queue (events.py).
The API SSE endpoint drains that queue and forwards events to the browser,
making the UI feel alive during segmentation.
"""

from __future__ import annotations

import asyncio
import logging
import operator
from collections import defaultdict
from typing import Annotated, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from backend.config import Config
from backend.infra.crm.airtable import AirtableClient
from backend.infra.db import client as db

from . import events as ev
from .scorer import (
    compute_composite,
    compute_goal_weights,
    compute_tier_cutoffs,
    extract_display_info,
    extract_goal_keywords,
    score_capacity,
    score_engagement,
    score_post_signal,
    score_topics,
    score_trajectory,
    score_warm_path,
    tier_from_distribution,
    _DEFAULT_WEIGHTS,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 200  # contacts per parallel Send node
_EMBED_SEM = asyncio.Semaphore(4)  # cap concurrent OpenAI calls


# ── State ────────────────────────────────────────────────────────────────────


class ScoredContact(TypedDict):
    record_id: str
    tier: str
    composite_score: float
    score_breakdown: dict  # per-component scores for UI + audit
    warm_path_data: Optional[dict]
    contact_snapshot: (
        dict  # {name, title, company, email} — avoids re-fetching Airtable
    )


class SegmentationState(TypedDict):
    campaign_id: int
    base_id: str
    table_id: str
    goal: str
    mapping_id: Optional[int]

    contacts: list[dict]  # raw Airtable records [{id, fields}]
    goal_embedding: list[float]  # 1536-dim OpenAI vector
    rag_scores: dict[str, float]  # record_id → cosine similarity [0, 1]
    goal_keywords: frozenset[str]  # extracted from goal for topic scoring
    goal_weights: dict[str, float]  # goal-adaptive composite weights (LLM-derived)
    field_map: dict[str, str]  # canonical_key → airtable_field_name from saved mapping

    # operator.add merges slices returned by parallel score_batch nodes
    batch_results: Annotated[list[ScoredContact], operator.add]

    tier_counts: dict[str, int]
    error: Optional[str]


# ── I/O helpers (called inside nodes) ────────────────────────────────────────


async def _fetch_contacts(base_id: str, table_id: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    crm = AirtableClient()
    table = crm.api.table(base_id, table_id)
    return await loop.run_in_executor(None, table.all)


async def _embed_text(text: str) -> list[float]:
    loop = asyncio.get_event_loop()

    def _call() -> list[float]:
        from openai import OpenAI

        c = OpenAI(api_key=Config.OPENAI_API_KEY)
        res = c.embeddings.create(model="text-embedding-3-small", input=[text])
        return res.data[0].embedding

    async with _EMBED_SEM:
        return await loop.run_in_executor(None, _call)


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def load_and_embed(state: SegmentationState, config: RunnableConfig) -> dict:
    """
    Fetch contacts from Airtable AND embed the campaign goal concurrently.
    Both are blocking I/O — asyncio.gather halves the wait time.
    return_exceptions=True ensures one failure doesn't silently swallow the other.
    """
    campaign_id = state["campaign_id"]
    await ev.emit(
        campaign_id,
        {
            "type": "progress",
            "step": "load",
            "message": "Loading contacts and embedding goal...",
        },
    )

    results = await asyncio.gather(
        _fetch_contacts(state["base_id"], state["table_id"]),
        _embed_text(state["goal"]),
        compute_goal_weights(state["goal"]),  # runs concurrently — no added latency
        return_exceptions=True,
    )
    contacts, goal_embedding, goal_weights = results

    if isinstance(contacts, Exception):
        raise RuntimeError(f"Airtable fetch failed: {contacts}") from contacts
    if isinstance(goal_embedding, Exception):
        raise RuntimeError(
            f"Goal embedding failed: {goal_embedding}"
        ) from goal_embedding
    if isinstance(goal_weights, Exception):
        logger.warning("Goal weights failed (%s) — using defaults", goal_weights)
        goal_weights = dict(_DEFAULT_WEIGHTS)

    await ev.emit(
        campaign_id,
        {
            "type": "progress",
            "step": "load",
            "message": f"Loaded {len(contacts)} contacts",
            "count": len(contacts),
            "goal_weights": goal_weights,
        },
    )
    # Build field_map from the saved mapping so extract_display_info
    # uses exact Airtable field names instead of guessing.
    field_map: dict[str, str] = {}
    mapping_id = state.get("mapping_id")
    if mapping_id:
        try:
            mapping = await db.get_field_mapping_by_id(mapping_id)
            if mapping:
                field_map = {
                    v["canonical_key"]: v["airtable_name"]
                    for v in mapping["mappings"].values()
                    if v.get("canonical_key") and v.get("airtable_name")
                }
        except Exception as e:
            logger.warning(f"Could not load mapping {mapping_id}: {e}")

    return {
        "contacts": contacts,
        "goal_embedding": goal_embedding,
        "goal_keywords": extract_goal_keywords(state["goal"]),
        "goal_weights": goal_weights,
        "field_map": field_map,
    }


async def rag_score_all(state: SegmentationState, config: RunnableConfig) -> dict:
    """
    Single bulk pgvector query — O(n) in Postgres, not N round-trips.
    Contacts not yet indexed get rag=0.0; segmentation continues with partial info.
    This is graceful degradation: the first campaign works even before embeddings
    are fully built.
    """
    campaign_id = state["campaign_id"]
    await ev.emit(
        campaign_id,
        {
            "type": "progress",
            "step": "rag",
            "message": "Computing semantic relevance scores...",
        },
    )

    vector_str = "[" + ",".join(str(x) for x in state["goal_embedding"]) + "]"

    try:
        rag_scores = await db.get_rag_scores(
            state["base_id"], state["table_id"], vector_str
        )
    except Exception as e:
        logger.warning(
            f"Campaign {campaign_id}: RAG query failed ({e}) — continuing with rag=0"
        )
        rag_scores = {}

    indexed = len(rag_scores)
    total = len(state["contacts"])

    if indexed == 0:
        await ev.emit(
            campaign_id,
            {
                "type": "warning",
                "step": "rag",
                "message": (
                    "No embeddings found — Campaign Match score will be 0 for all contacts. "
                    "Run Embedding on your job first for semantic relevance scoring."
                ),
                "indexed": 0,
                "total": total,
            },
        )
    else:
        await ev.emit(
            campaign_id,
            {
                "type": "progress",
                "step": "rag",
                "message": f"Semantic scores ready ({indexed}/{total} contacts indexed)",
                "indexed": indexed,
                "total": total,
            },
        )
    return {"rag_scores": rag_scores}


def route_batches(state: SegmentationState) -> list[Send]:
    """
    Fan-out: one Send per BATCH_SIZE slice of the contact list.
    Each Send target (score_batch) runs independently — LangGraph executes
    them concurrently and waits for all to complete before finalize runs.

    5 000 contacts @ BATCH_SIZE=200 → 25 parallel nodes.
    """
    contacts = state["contacts"]
    rag_scores = state["rag_scores"]
    campaign_id = state["campaign_id"]

    goal_keywords = state["goal_keywords"]
    goal_weights = state.get("goal_weights", _DEFAULT_WEIGHTS)
    field_map = state.get("field_map", {})

    return [
        Send(
            "score_batch",
            {
                "campaign_id": campaign_id,
                "contacts": contacts[i : i + BATCH_SIZE],
                "rag_scores": rag_scores,
                "goal_keywords": goal_keywords,
                "goal_weights": goal_weights,
                "field_map": field_map,
                "batch_index": i // BATCH_SIZE,
            },
        )
        for i in range(0, len(contacts), BATCH_SIZE)
    ]


def score_batch(state: dict) -> dict:
    """
    Pure-Python scoring — no I/O, no LLM.
    Called N times in parallel via the Send fan-out.
    Returns {"batch_results": [ScoredContact, ...]} which operator.add
    appends into SegmentationState.batch_results.
    """
    results: list[ScoredContact] = []

    goal_weights = state.get("goal_weights") or _DEFAULT_WEIGHTS

    for record in state["contacts"]:
        record_id: str = record["id"]
        fields: dict = record.get("fields", {})

        warm_norm, warm_data = score_warm_path(fields)
        post_sig = score_post_signal(fields)
        rag = state["rag_scores"].get(record_id, 0.0)
        capacity = score_capacity(fields)
        trajectory = score_trajectory(fields)
        engagement = score_engagement(fields)
        topics = score_topics(fields, state.get("goal_keywords", frozenset()))

        composite = compute_composite(
            warm_path=warm_norm,
            post_signal=post_sig,
            rag=rag,
            capacity=capacity,
            trajectory=trajectory,
            engagement=engagement,
            topics=topics,
            weights=goal_weights,
        )

        results.append(
            ScoredContact(
                record_id=record_id,
                tier="",  # assigned in finalize, once the full distribution is known
                composite_score=composite,
                score_breakdown={
                    "warm_path": warm_norm,
                    "post_signal": post_sig,
                    "rag": rag,
                    "capacity": capacity,
                    "trajectory": trajectory,
                    "topics": topics,
                    "engagement": engagement,
                    "_weights": goal_weights,
                },
                warm_path_data=warm_data,
                contact_snapshot=extract_display_info(
                    fields, state.get("field_map", {})
                ),
            )
        )

    return {"batch_results": results}


async def finalize(state: SegmentationState, config: RunnableConfig) -> dict:
    """
    Collect all batch results, sort within tiers by composite score DESC,
    bulk-insert into campaign_contacts, and mark the campaign ready.
    """
    campaign_id = state["campaign_id"]
    results = state["batch_results"]

    await ev.emit(
        campaign_id,
        {
            "type": "progress",
            "step": "finalize",
            "message": f"Scored {len(results)} contacts — assigning tiers...",
        },
    )

    # Distribution-relative tiering: cutoffs are derived from THIS campaign's
    # actual score spread, then lifted by single-signal promotion floors.
    t1_cut, t2_cut = compute_tier_cutoffs([r["composite_score"] for r in results])
    logger.info(
        "Campaign %s tier cutoffs: t1>=%.3f t2>=%.3f", campaign_id, t1_cut, t2_cut
    )
    for r in results:
        r["tier"] = tier_from_distribution(
            r["composite_score"], r["score_breakdown"], t1_cut, t2_cut
        )

    # Group → sort each tier by composite score DESC
    by_tier: dict[str, list[ScoredContact]] = defaultdict(list)
    for r in results:
        by_tier[r["tier"]].append(r)
    for tier_list in by_tier.values():
        tier_list.sort(key=lambda c: -c["composite_score"])

    tier_counts = {
        "tier_1": len(by_tier.get("tier_1", [])),
        "tier_2": len(by_tier.get("tier_2", [])),
        "tier_3": len(by_tier.get("tier_3", [])),
    }

    await ev.emit(
        campaign_id,
        {
            "type": "progress",
            "step": "finalize",
            "message": (
                f"Tier 1: {tier_counts['tier_1']} · "
                f"Tier 2: {tier_counts['tier_2']} · "
                f"Tier 3: {tier_counts['tier_3']}"
            ),
            "tier_counts": tier_counts,
        },
    )

    # Ordered: tier_1 first (highest score), then tier_2, then tier_3
    ordered = (
        by_tier.get("tier_1", [])
        + by_tier.get("tier_2", [])
        + by_tier.get("tier_3", [])
    )

    db_contacts = [
        {
            "airtable_record_id": r["record_id"],
            "tier": r["tier"],
            "composite_score": r["composite_score"],
            "score_breakdown": r["score_breakdown"],
            "ai_reasoning": None,  # generated on-demand in review queue
            "warm_path_data": r.get("warm_path_data"),
            "contact_snapshot": r.get("contact_snapshot", {}),
        }
        for r in ordered
    ]

    await ev.emit(
        campaign_id,
        {
            "type": "progress",
            "step": "persist",
            "message": f"Saving {len(db_contacts)} contacts...",
        },
    )

    await db.bulk_insert_campaign_contacts(campaign_id, db_contacts)
    await db.set_campaign_tier_counts(
        campaign_id,
        tier_1=tier_counts["tier_1"],
        tier_2=tier_counts["tier_2"],
        tier_3=tier_counts["tier_3"],
    )
    await db.update_campaign_status(campaign_id, "ready")

    # Generate tier audience insights in the background (non-blocking)
    asyncio.create_task(_generate_and_save_insights(
        campaign_id=campaign_id,
        goal=state["goal"],
        by_tier=by_tier,
    ))

    await ev.emit(
        campaign_id,
        {
            "type": "complete",
            "message": "Segmentation complete",
            "tier_counts": tier_counts,
            "total": len(results),
        },
    )
    await ev.close(campaign_id)

    return {"tier_counts": tier_counts}


async def _generate_and_save_insights(
    campaign_id: int,
    goal: str,
    by_tier: dict,
) -> None:
    """Background task: generate 1-2 sentence audience insight for each tier and persist."""
    from backend.agents.outreach import generate_tier_insight
    from backend.outreach.signal_scanner import scan_tier_signals

    insights: dict[str, str] = {}
    for tier_key, contacts in by_tier.items():
        if not contacts:
            continue
        try:
            # Build minimal samples list for the insight generator
            samples = [
                {"contact_snapshot": c.get("contact_snapshot", {}), "score_breakdown": c.get("score_breakdown", {})}
                for c in contacts[:20]
            ]
            scan = await scan_tier_signals(campaign_id, tier_key)
            insights[tier_key] = await generate_tier_insight(goal, tier_key, scan, samples)
        except Exception as e:
            logger.warning(f"Insight generation for {tier_key} failed: {e}")
            insights[tier_key] = ''

    try:
        await db.save_tier_insights(
            campaign_id,
            tier_1_insight=insights.get("tier_1", ""),
            tier_2_insight=insights.get("tier_2", ""),
            tier_3_insight=insights.get("tier_3", ""),
        )
    except Exception as e:
        logger.warning(f"Failed to save tier insights for campaign {campaign_id}: {e}")


# ── Graph assembly ────────────────────────────────────────────────────────────


def _build() -> StateGraph:
    g = StateGraph(SegmentationState)

    g.add_node("load_and_embed", load_and_embed)
    g.add_node("rag_score_all", rag_score_all)
    g.add_node("score_batch", score_batch)
    g.add_node("finalize", finalize)

    g.add_edge(START, "load_and_embed")
    g.add_edge("load_and_embed", "rag_score_all")
    g.add_conditional_edges("rag_score_all", route_batches, ["score_batch"])
    g.add_edge("score_batch", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


_graph = _build()


# ── Public entry point ────────────────────────────────────────────────────────


async def run_segmentation(
    campaign_id: int,
    base_id: str,
    table_id: str,
    goal: str,
    mapping_id: Optional[int] = None,
) -> None:
    """
    Run the full segmentation pipeline for a campaign.

    Call events.register(campaign_id) BEFORE this so no events are lost.
    Handles its own error state — marks campaign 'failed' on any unhandled exception.
    """
    await ev.emit(campaign_id, {"type": "started", "message": "Segmentation started"})
    await db.update_campaign_status(campaign_id, "segmenting")

    try:
        await _graph.ainvoke(
            {
                "campaign_id": campaign_id,
                "base_id": base_id,
                "table_id": table_id,
                "goal": goal,
                "mapping_id": mapping_id,
                "contacts": [],
                "goal_embedding": [],
                "rag_scores": {},
                "goal_keywords": frozenset(),
                "goal_weights": dict(_DEFAULT_WEIGHTS),
                "field_map": {},
                "batch_results": [],
                "tier_counts": {},
                "error": None,
            }
        )
    except Exception as e:
        logger.error(f"Campaign {campaign_id}: segmentation failed: {e}", exc_info=True)
        # Delete the campaign — it has no contacts so it's useless noise in the UI.
        # The SSE error event tells the client before the record disappears.
        await ev.emit(campaign_id, {"type": "error", "message": str(e)})
        await ev.close(campaign_id)
        await db.delete_campaign(campaign_id)
