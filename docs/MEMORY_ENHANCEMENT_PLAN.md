# Hybrid Memory Integration Plan

## Target architecture

Prompt assembled per turn by `dreamescape_ai`:

```text
[SYSTEM]      persona + scene (existing PromptService)
[STORY SO FAR] rolling summary                    ← narrative flow
[KNOWN FACTS]  Graphiti current-state facts       ← relationships, plot state
[MEMORIES]     pgvector verbatim chunks           ← exact wording, callbacks
[HISTORY]      recent verbatim messages (budgeted)
[REMINDER]     condensed persona + scene state
[USER]         new message
```

Each memory source answers what it's best at:
- **Summary** — what happened, in order (cheap, always present)
- **Graph facts** — what is true *now* (fact invalidation handles arcs/reversals)
- **Vector chunks** — what exactly was said (verbatim recall)

Write path is fully asynchronous: user-facing generation is never blocked by memory ingestion.

---

## Phase 0 — Shared foundations (dreamescape_ai)

**0.1 Prompt builder refactor.** Extend `PromptService` from a single-string builder to a
sectioned builder: `build_prompt_sections(...) -> PromptSections` (pydantic model with
`system`, `summary`, `facts`, `memories`, `reminder`). A renderer flattens sections into
the existing `LLMRequest.system_prompt` string — **no agent changes required**. Sections
render empty when a source has nothing, so every phase below is independently shippable.

**0.2 Token budgeter.** Utility `budget(sections, history, limit)`:
- Never evicted: `system`, `reminder`, `user message`.
- Fixed caps: summary ≤ 500 tok, facts ≤ 400 tok, memories ≤ 600 tok.
- History gets the remainder, trimmed oldest-first.
- Limit = `ChatSettings.contextLimitOverride` or model default.

**0.3 Memory orchestrator.** New `MemoryService` behind port `IMemoryService`:
- `enrich(chat_id, user_msg) -> PromptSections partial` — fan-out to summary/vector/graph
  gateways **concurrently** (`asyncio.gather`, per-source timeout ~800ms, failure of any
  source degrades to empty section + warning log, never a user-facing error).
- `ingest(chat_id, message_id, user_msg, model_reply)` — background task fired in the
  RabbitMQ result consumer *after* the model reply is persisted and pushed to SSE.

**0.4 Ports** (all optional-off via config flags):
- `ISummaryGateway`, `IVectorMemoryGateway`, `IGraphMemoryGateway`.

Wire into `LLMChatsService.send_message`: replace the unbounded history load with
`summary + tail`, call `enrich`, build sections, budget, publish.

---

## Phase 1 — Reminder + rolling summary

1. `build_reminder(...)`: ~100–150 token condensed persona/scene block (from existing
   `Character.system_prompt` / `Scene` data), placed last before the user message.
2. Alembic migration: `conversation_summaries` (append-only:
   `id, chat_id, from_message_id, to_message_id, content, token_count, supersedes_id, model, created_at`,
   unique `(chat_id, to_message_id)`).
3. `SummaryService.fold(chat_id)`: background; triggers when tail > `SUMMARY_TRIGGER_TOKENS`
   (default 2000); folds `old summary + oldest chunk → new summary` via cheap model
   (`claude_haiku` / `deepseek-chat` through the existing agent queue); INSERT-only, retry-safe.
4. Read path: latest summary + messages after `to_message_id`.

**Exit criteria:** persona stable at 50+ turns; prompt tokens plateau; mock model E2E green.

## Phase 2 — pgvector verbatim memory

1. Enable `pgvector`; table `chat_memories(id, chat_id, message_id, content, embedding vector(1536))`,
   HNSW cosine index. (k8s_deploy: ensure Postgres image ships pgvector — e.g. `pgvector/pgvector:pg16`.)
2. `PgVectorMemoryGateway`:
   - `store`: embed user+model messages on `ingest` (OpenAI `text-embedding-3-small`,
     behind an `IEmbedder` port for later local model swap).
   - `retrieve(chat_id, query, k=5, max_distance=0.5)`, **excluding messages already in the
     verbatim tail** (`message_id <= latest_summary.to_message_id`).
3. Renders into `[MEMORIES]` as quoted excerpts with turn attribution.

**Exit criteria:** long-range verbatim callback retrievable at 100+ turns; no duplicates
with history tail; retrieval p95 < 300ms.

## Phase 3 — Graphiti graph facts

1. Infra (k8s_deploy): FalkorDB deployment + PVC + service; docker-compose entry for local dev.
   Add `graphiti-core[falkordb]` to dreamescape_ai.
2. `GraphitiMemoryGateway`:
   - `store`: `add_episode(episode_body="[UserChar] msg\n[Char] reply", group_id=str(chat_id),
     reference_time=...)`; cheap extraction model; `SEMAPHORE_LIMIT` low; custom Pydantic
     entity types: `Character`, `Relationship`, `PlotEvent`, `Promise`.
   - `retrieve`: `search(query, group_id)` → **valid facts only** → `[KNOWN FACTS]` lines.
3. Ingestion runs in the same `ingest` background task, after pgvector store (graph ingestion
   is the slow/expensive step; its failure must not block anything).
4. Lifecycle: on chat deletion, delete `group_id` graph + memories + summaries (one cleanup task).
5. **Gate this phase on the spike's go decision** (cost/quality report from the Graphiti spike issue).

**Exit criteria (probe tests from spike):** after a relationship reversal, `[KNOWN FACTS]`
contains the *current* state and not the stale one; ingestion cost per turn within budget
(set target, e.g. <$0.002/turn with haiku-class extraction).

## Phase 4 — Tuning & product surface

- Deduplicate across sections: if a graph fact and a vector chunk say the same thing, drop the
  chunk (embedding similarity between fact and chunk > threshold).
- Per-chat memory config in `ChatSettings` (e.g. graph memory only for long chats / premium tier —
  pgvector+summary is the default tier).
- Token counter API + context usage in message responses (feeds the UI bar).
- Manual controls: view/edit current summary (insert superseding row), pin messages
  (excluded from folding, always in tail).
- Eval harness: scripted 100-turn transcripts with probes (reversal, callback, multi-hop),
  run against each phase to catch regressions.

---

## Rollout & risk

| Risk | Mitigation |
|---|---|
| Memory sources add latency | Concurrent fan-out, hard timeouts, degrade-to-empty |
| Graphiti extraction errors become canonical wrong facts | Cheap-model eval in spike; keep pgvector chunks as corrective raw context; facts section capped |
| Cost blow-up from per-turn graph ingestion | Ingest per-turn only above a chat-length threshold; batch small turns; cheap model |
| FalkorDB ops on k8s | PVC + backup job; feature-flagged so outage = graceful degradation |
| Prompt regressions | DEBUG section logging already exists; eval harness in Phase 4 |

Feature flags per source (`SUMMARY_ENABLED`, `VECTOR_MEMORY_ENABLED`, `GRAPH_MEMORY_ENABLED`)
allow instant rollback of any layer independently.

## Dependency order

Phase 0 → Phase 1 → Phase 2 → (spike go/no-go) → Phase 3 → Phase 4.
Phases 1–2 deliver the 20–30-message drift fix on their own; Phase 3 targets the
long-arc "she forgot we broke up" class of failures.