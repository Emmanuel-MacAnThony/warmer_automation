# Scalability Issues

Document for tracking scale problems and potential solutions.

---

## Issue #1: Conversation History Bloat

**Problem**: Frontend sends full conversation history on every request with no pruning. History grows indefinitely until page refresh.

**Impact**: Will eventually hit LLM context limits (200k tokens for Claude) and degrade performance. Each request becomes slower and more expensive.

**Solution**: Implement sliding window (keep last 10-20 messages) or token-based truncation (max 10k tokens). Consider summarizing old context.

---

## Issue #2: HITL Workflow Storage (In-Memory Dict)

**Problem**: `_interrupted_workflows` dict (server.py:37) stores HITL workflows in memory. Lost on restart, can't scale across multiple servers, no expiration.

**Impact**: Workflows lost on server restart/crash. Can't load balance. Memory grows indefinitely. Users lose pending approvals.

**Solution**: Replace with Redis. Use TTL (1 hour expiration). Enables multi-server deployment and persistence. Key: `hitl:workflow:{record_id}`.

---
