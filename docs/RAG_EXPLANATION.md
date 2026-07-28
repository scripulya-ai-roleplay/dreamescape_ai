# Hybrid Memory (Retrieval-Augmented Chat) — Bottom-Up Explanation

This document explains the chat memory system introduced by `docs/MEMORY_ENHANCEMENT_PLAN.md`
(Phases 0, 1, 2, 3, 4). It is written **bottom-up**: it starts at the data layer and climbs to the
user-facing API, so each layer is explained only in terms of the layers already covered.

The system is a form of **retrieval-augmented generation (RAG)** layered on a roleplay chat:
besides recent verbatim history, every turn's prompt is augmented with a rolling *summary* of the
story so far and *verbatim memories* retrieved by semantic similarity from a pgvector store.

```
[SYSTEM]        persona + scene (existing PromptService)
[STORY SO FAR]  rolling summary of the conversation      ← narrative compression
[KNOWN FACTS]   Graphiti/FalkorDB current-state facts    ← invalidation-aware (reversals handled)
[MEMORIES]      pgvector verbatim chunks                 ← semantic recall (RAG)
[HISTORY]       recent verbatim messages (budgeted)
[REMINDER]      condensed persona + scene, placed last   ← re-anchoring
[USER]          the new message
```

Each source answers what it is best at:

- **Summary** — what happened, in order (cheap, always present once the chat is long enough).
- **Graph facts** — what is true *now* (relationships, plot state; fact invalidation handles arcs/reversals).
- **Vector chunks** — what was *exactly* said (verbatim callbacks, long-range recall).
- **Reminder** — who the characters are and what the setting is (persona drift defence).

Ingestion (writing summaries + embeddings) is **fully asynchronous**: user-facing generation is
never blocked by it.

---

## Layer 0 — Data (PostgreSQL + pgvector)

Schema lives in `scripts/init.sql` (applied on a fresh volume) and a matching idempotent migration
`scripts/migrations/20260727_hybrid_memory.sql` (for already-initialized volumes). The ORM mirrors
in `src/infrastructure/database/models.py`.

### `conversation_summaries` — the rolling summary log

Append-only. Editing the summary does not mutate a row; it inserts a new one that *supersedes* the
old, so history is never lost.

```sql
CREATE TABLE conversation_summaries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id         UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    from_message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    to_message_id   UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    token_count     INTEGER NOT NULL DEFAULT 0,
    supersedes_id   UUID REFERENCES conversation_summaries(id) ON DELETE SET NULL,
    model           VARCHAR(100) NOT NULL,            -- e.g. "gpt-4o-mini" or "manual"
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (chat_id, to_message_id)                   -- redelivery-safe fold
);
CREATE INDEX idx_conversation_summaries_chat_created ON conversation_summaries(chat_id, created_at DESC);
CREATE INDEX idx_conversation_summaries_current      ON conversation_summaries(chat_id) WHERE supersedes_id IS NULL;
```

- `to_message_id` is the high-water mark: the summary covers messages up to and including it.
- `UNIQUE (chat_id, to_message_id)` makes a fold idempotent — a re-delivered RabbitMQ result that
  re-runs the fold tries to insert the same `(chat_id, to_message_id)` and the constraint rejects it.
- The partial index `WHERE supersedes_id IS NULL` makes "the current summary" a cheap lookup.

### `chat_memories` — the verbatim vector store

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chat_memories (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id    UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    role       VARCHAR(50) NOT NULL,                  -- 'user' | 'model'
    content    TEXT NOT NULL,
    embedding  vector(1536) NOT NULL,                 -- matches the configured embedder
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (chat_id, message_id)                      -- redelivery-safe store
);
CREATE INDEX idx_chat_memories_chat_message ON chat_memories(chat_id, message_id);
CREATE INDEX idx_chat_memories_hnsw         ON chat_memories
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
```

- `vector(1536)` matches OpenAI `text-embedding-3-small`. The dimension is **baked into the column
  type**; switching to an embedder with a different dimension requires `ALTER`ing the column and
  re-embedding all rows (see Layer 8 — Startup).
- `UNIQUE (chat_id, message_id)` + `ON CONFLICT DO NOTHING` makes storing a message idempotent.
- HNSW + `vector_cosine_ops` accelerates nearest-neighbour search by cosine distance.

Both tables `ON DELETE CASCADE` off `chats`/`messages`, so deleting a chat cleans up its summaries
and vector memories automatically; the FalkorDB graph partition is dropped explicitly (Layer 5).

---

## Layer 1 — Ports (the abstractions)

Everything above the database talks through interfaces in `src/application/ports/`, so any vendor
or storage can be swapped without touching business logic.

| Port | File | Purpose |
|---|---|---|
| `IEmbedder` | `embedder.py` | `embed(texts) -> list[list[float]]` + `dimension`. Vendor-pluggable (OpenAI today; Google/other later). |
| `ISummaryModel` | `summary_model.py` | `summarize(prior_summary, messages) -> str`. Vendor-pluggable. |
| `ISummaryGateway` | `memory.py` | `latest(chat_id)`, `insert(summary)` — summary table access. |
| `IVectorMemoryGateway` | `memory.py` | `store(...)`, `retrieve(chat_id, query, k, max_distance, exclude_message_ids, dedup_embedding)` — vector store access. |
| `IGraphMemoryGateway` | `memory.py` | `store(chat_id, user_msg, model_reply, reference_time)`, `retrieve(...) -> list[str]`, `delete_group(chat_id)`. `Null…` when `GRAPH_MEMORY_ENABLED=false`, else `GraphitiMemoryGateway`. |
| `IMemoryService` | `memory.py` | `enrich(...)` (read path) + `ingest(...)` (write path). |
| `IMemoryControlService` | `memory.py` | `current_summary`, `set_summary`, `context_usage` (user-facing controls). |
| `TokenCounter` | `chats/budgeter.py` | `count(text)`, `count_message(msg)`. tiktoken with a heuristic fallback. |

Supporting DTOs in `memory.py`: `MemoryChunk(message_id, role, content, distance)` and
`EnrichResult(sections, tail)`.

> **Why ports?** The user explicitly wanted embedder/summary vendors to be swappable (OpenAI today,
> possibly Google or others later). Every external dependency is behind an interface, and only the
> concrete gateway (Layer 2) knows which vendor is in use.

---

## Layer 2 — Gateways (concrete adapters)

`src/infrastructure/gateways/`. These are the only place vendor/storage details leak in.

- **`SummaryGateway`** (`summary_gateway.py`) — `latest()` selects the newest non-superseded row;
  `insert()` is flush-only (the UoW owns the commit, see Layer 5).
- **`PgVectorMemoryGateway`** (`vector_memory_gateway.py`)
  - `store`: embeds the content, `INSERT ... ON CONFLICT (chat_id, message_id) DO NOTHING`.
  - `retrieve`: sets `hnsw.ef_search`, embeds the query, orders by `embedding.cosine_distance(query)`,
    over-fetches `k*3`, then post-filters by `max_distance`, excludes the tail message ids, drops
    chunks too close to the summary embedding (dedup), and trims to `k`.
- **`OpenAIEmbedder`** (`openai_embedder.py`) — `AsyncOpenAI.embeddings.create`, returns vectors
  sorted by index; `dimension` is config-driven.
- **`OpenAISummaryModel`** (`openai_summary_model.py`) — `AsyncOpenAI.chat.completions.create` with a
  tight "continue the rolling summary" prompt, `max_tokens = SUMMARY_TOKEN_CAP`.
- **`NullGraphMemoryGateway`** (`null_graph_memory_gateway.py`) — no-op stand-in when
  `GRAPH_MEMORY_ENABLED=false`.
- **`GraphitiMemoryGateway`** (`graphiti_memory_gateway.py`) — the Phase 3 graph memory.
  - Builds a `Graphiti` client **lazily** (on first use, inside the event loop) with a
    `FalkorDriver` + `OpenAIClient` (extraction model `GRAPH_EXTRACTION_MODEL`) + `OpenAIEmbedder`.
    Lazy construction means the backend starts fine with FalkorDB absent; the first store/retrieve
    connects, and any failure degrades through the caller's try/except.
  - `store`: `graphiti.add_episode(group_id=str(chat_id), episode_body="[User] …\n[Character] …",
    reference_time=…, entity_types=ENTITY_TYPES)` — Graphiti extracts entities/edges and handles
    dedup + invalidation internally.
  - `retrieve`: `graphiti.search(query, group_ids=[chat_id])` → keep only edges with
    `invalid_at is None and expired_at is None` (current facts), cap at `GRAPH_MEMORY_MAX_FACTS`.
  - `delete_group`: `MATCH (n {group_id: $group_id}) DETACH DELETE n` — the FalkorDB partition has
    no FK cascade, so chat deletion drops it explicitly.
  - **Custom entity types** (`src/application/memory/graph_entities.py`): `Character`, `PlotEvent`,
    `Promise` (`EntityNode` subclasses) passed via `entity_types=` so extraction classifies them
    distinctly. Edges use Graphiti's default `EntityEdge` (each edge is itself a `fact`).

> **The agent stays dumb.** Embeddings and summaries run **directly in the backend**, not through
> `scripulya_agent`. The agent remains a pure "given an assembled prompt, generate" worker. Memory
> ingestion is a backend concern (it reads/writes the backend's own database), so routing it through
> the agent would force DB access or RPC plumbing onto a worker that intentionally has neither.

A shared `AsyncOpenAI` client (APP-scoped in DI) backs both `OpenAIEmbedder` and `OpenAISummaryModel`.

---

## Layer 3 — Services (business logic)

`src/application/memory/`.

### `SummaryService` (`summary_service.py`) — the rolling fold

- `maybe_fold(chat_id)`: reads the current summary's `to_message_id`, loads the tail after it, sums
  its tokens; if below `SUMMARY_TRIGGER_TOKENS` (default 2000) → no-op. Otherwise calls `_fold`.
- `_fold`: selects the oldest batch that fits `SUMMARY_FOLD_BATCH_TOKENS`, asks `ISummaryModel` to
  fold `prior_summary + batch → new summary`, and inserts a new row with
  `supersedes_id = current.id`. `IntegrityError` (redelivery duplicate) is swallowed.

### `MemoryService` (`service.py`) — orchestrates the two paths

**Read — `enrich(chat_id, user_msg, memory_settings) -> EnrichResult`:**
1. Resolve per-chat + global flags → `summary_enabled`, `vector_enabled`.
2. Fetch the latest summary (for the `[STORY SO FAR]` text **and** the tail boundary).
3. Load the bounded tail after `to_message_id` (`HISTORY_MAX_TAIL`, or full when summary is off).
   This single tail query feeds both the history section and the vector *exclude* set.
4. `asyncio.gather` the memory sources (vector recall + graph facts), each wrapped in `_safe`.
5. Return `EnrichResult(sections=summary/memories/facts, tail)`.

`_safe(coro, default)` wraps each source in `asyncio.wait_for(MEMORY_SOURCE_TIMEOUT_MS)` and catches
everything: a slow/failing source degrades to an empty section + a warning log, never a user error.

**Write — `ingest(chat_id, model_reply_message_id)`:**
1. Idempotency guard: Redis `SETNX memory:ingested:{chat_id}:{message_id}` (TTL 7 days). Skip if set.
2. If vector enabled: store the user message + the model reply (in one `async with uow`).
3. If graph enabled: `graph_gateway.store(chat_id, user_msg, model_reply, reference_time)` — runs
   *after* the vector store; graph ingestion is the slow/expensive step.
4. If summary enabled: `summary_service.maybe_fold(chat_id)`.

Each step is independently try/excepted — a vector, graph, or summary failure never blocks the
others.

The read path does **fact-vs-chunk dedup**: after retrieving chunks and facts concurrently,
`_dedup_chunks_vs_facts` embeds the (few) facts and drops any verbatim chunk whose stored embedding
is within `1 - MEMORY_SUMMARY_DEDUP_SIMILARITY` (cosine) of a fact — the fact is already in
`[KNOWN FACTS]`, so the chunk is redundant.

### `MemoryControlService` (`memory_control_service.py`) — user-facing controls

- `current_summary(chat_id, actor_id)` — latest non-superseded row.
- `set_summary(chat_id, content, actor_id)` — inserts a `model="manual"` row that supersedes the
  current one (so the partial index immediately picks it up as "latest").
- `context_usage(chat_id, actor_id)` — rebuilds the sections + tail and runs `budget()` to report the
  per-section token breakdown and total (feeds the UI context bar).

### `MemoryIngestDispatcher` (`ingest_dispatcher.py`) — the async bridge

`dispatch(chat_id, message_id)` is **synchronous and fire-and-forget**: it creates an `asyncio.Task`
that opens its **own** dishka REQUEST scope, resolves `IMemoryService`, and runs `ingest`. This is the
critical correctness property — the ingest task never shares the request-scoped DB session of the
RabbitMQ handler that triggered it. It mirrors the established `GenerationWatchdog` pattern and holds
an `_inflight` set so the task is not garbage-collected. Any exception is logged and swallowed.

---

## Layer 4 — Prompt assembly + budgeting

`src/application/chats/`.

### `PromptSections` + `render_system_prompt` (`prompt_sections.py`)

A small pydantic model with five string fields (`system, summary, facts, memories, reminder`) and a
pure renderer that:

- Emits the `system` block **without a header** (it *is* the base system prompt).
- Emits each non-empty memory section with a bracketed header (`[STORY SO FAR]`, `[KNOWN FACTS]`,
  `[MEMORIES]`, `[REMINDER]`).
- Omits empty sections entirely.

Because `system` is header-less and the rest are empty by default, `render_system_prompt` with only
`system` populated is **byte-identical** to the pre-feature `build_system_prompt` output. That is the
rollout-safety invariant: with both memory flags off, nothing observable changes.

### `PromptService` (`prompt_service.py`)

- `build_prompt_sections(scene, characters, persona) -> PromptSections` — fills `system` only.
- `build_system_prompt(...)` — now just `render_system_prompt(build_prompt_sections(...))`. Existing
  callers and tests are unchanged.
- `build_reminder(...)` — a condensed persona/scene block (character name + first ~30 words of each
  `system_prompt`; scene title + first sentence of `background_prompt`), capped at
  `REMINDER_TOKEN_CAP`. Placed last so it re-anchors the persona right before the new message.

### `budget` (`budgeter.py`)

`budget(sections, history, user_msg, limit, counter) -> BudgetResult`:

- **Never evicted**: `system`, `reminder`, and the user message.
- **Capped**: `summary ≤ SUMMARY_TOKEN_CAP` (500), `memories ≤ MEMORIES_TOKEN_CAP` (600); the summary
  is truncated at a sentence boundary so it never reads as garbled.
- **History**: trimmed oldest-first to fit the remainder. Pinned indices are always kept.
- `limit = None` (the summary-off path) means **no trimming** — the full tail is forwarded, matching
  legacy behavior. Budgeting only kicks in when the rolling summary can recover what it drops.

`TokenCounter` has two implementations: `TiktokenCounter` (cl100k_base; ~10% approximate for
non-OpenAI models, which is fine for budgeting and never for billing) and `HeuristicTokenCounter`
(chars/4, used in tests and when tiktoken's BPE cannot load).

---

## Layer 5 — Wiring the read and write paths

### Read path — `LLMChatsService.send_message` (`chats/llm_service.py`)

```
get chat → authz → persona gate
→ chat_settings (for contextLimitOverride + memory flags)
→ memory_service.enrich(chat_id, msg, memory_settings)        # fills sections + returns tail
→ initial-message gate (rejected if no history and no greeting chosen)
→ fetch scene / characters / persona
→ sections.system = build_prompt_sections(...)
→ sections.{summary,memories,facts} = enriched.sections.*
→ sections.reminder = build_reminder(...)   (only when summary_enabled)
→ history = tail → UserMessageDTO list; compute pinned_indices
→ persist the user message (role=USER, always)
→ limit = contextLimitOverride or DEFAULT_CONTEXT_LIMIT  (None when summary off)
→ budgeted = budget(sections, history, user_msg, limit, counter)
→ system_prompt = render_system_prompt(budgeted.sections)
→ gateway.submit(chat_dto, budgeted.history, chat_settings, system_prompt)
```

Gates fire **before** scene/character resolution and persistence, matching the pre-feature contract.

### Write path — `controllers/rabbit/v1/llm.py`

The model reply arrives on the `llm.agent.result` queue. `_dispatch_agent_result`:

1. Logs provider failures.
2. Persists the reply (`append_model_message`) and pushes it to SSE.
3. **Only for `COMPLETED` replies**: calls `ingest_dispatcher.dispatch(chat_id, message.id)`.

`message.id` is the just-persisted reply row — this is how ingest knows what to embed/summarize
without a correlation id on `LLMResult`. The `dispatch` call returns immediately; the actual ingest
runs in the background task described in Layer 3.

### Dependency injection — `infrastructure/di.py`

- **APP scope** (stateless): `AsyncOpenAI`, `IEmbedder`, `ISummaryModel`, `IGraphMemoryGateway`
  (null), `TokenCounter` (tiktoken → heuristic fallback), `MemoryIngestDispatcher`.
- **REQUEST scope** (per-session): `ISummaryGateway`, `IVectorMemoryGateway`, `SummaryService`,
  `IMemoryService`, `IMemoryControlService`. `provide_chats_service` injects `memory_service` and
  `token_counter` into `LLMChatsService`.

All writes still commit through the single `PostgresqlUOW` seam — gateways are flush-only.

---

## Layer 6 — API (top)

`src/controllers/api/v1/memory.py`, all owner-checked:

| Method | Route | Behaviour |
|---|---|---|
| `GET` | `/api/v1/chats/{id}/summary` | Current (latest non-superseded) summary, or null. |
| `PUT` | `/api/v1/chats/{id}/summary` | Insert a `model="manual"` summary that supersedes the current one. |
| `GET` | `/api/v1/chats/{id}/context-usage` | `{sections: {...}, total, limit, system_prompt}` — the live budget breakdown. |

Per-chat configuration lives on `ChatSettings.memory`
(`src/application/chats/settings.py`):

```python
class MemorySettings(BaseModel):
    summaryEnabled: bool = True
    vectorMemoryEnabled: bool = True
    pinnedMessageIds: list[UUID] = []
```

Because `chat_settings.settings` is a JSONB column loaded with `ChatSettings(**row.settings)`, adding
this field with a default is **migration-free** for existing rows — old blobs validate against the
default. Pinning is a per-chat *view* of a message (not an intrinsic column on `messages`), so it
lives here. Effective flags are `global AND per-chat`.

---

## Layer 7 — End-to-end: one message, top to bottom

1. Client `POST /api/v1/messages` with a user message.
2. `send_message` authorises, enriches (summary + bounded tail + vector recall, concurrently with
   hard per-source timeouts), assembles the sectioned prompt, budgets it, and submits to the agent.
3. The agent generates (unchanged) and publishes the reply to `llm.agent.result`.
4. `_dispatch_agent_result` persists the reply, pushes it to SSE, and fires the ingest dispatcher.
5. Ingest (background, own session): embeds the user + model messages into `chat_memories`; if
   graph is on, `add_episode` extracts entities/edges into FalkorDB; if the tail grew past the
   threshold, folds a new `conversation_summaries` row.
6. The next turn's `enrich` picks up that new summary (so the oldest messages leave the verbatim
   tail but survive in `[STORY SO FAR]`), recalls old verbatim lines into `[MEMORIES]`, and surfaces
   current-state facts into `[KNOWN FACTS]` (with reversals invalidating stale facts).

---

## Layer 8 — Operations

### Deployment (`scripulya_deploy`)

- Postgres image `postgres:15` → **`pgvector/pgvector:pg15`** in both `docker-compose.yml` and
  `k8s/10-postgres.yaml`. Same major version → no data migration, just adds the extension.
- **FalkorDB** (`falkordb/falkordb`) for graph memory: a service + volume in `docker-compose.yml`
  and a StatefulSet + PVC in `k8s/14-falkordb.yaml`. Optional — only needed when
  `GRAPH_MEMORY_ENABLED=true`; the backend degrades to empty `[KNOWN FACTS]` without it.
- After changing `init.sql`, regenerate the k8s ConfigMap with `make gen-init-sql` (applies to a live
  cluster). Fresh volumes get the schema from `init.sql`; **existing** volumes need
  `scripts/migrations/20260727_hybrid_memory.sql` run once.
- Set `OPENAI_API_KEY` in the backend environment (Secret `scripulya-secrets`; included by
  `gen-secrets.sh`). Without it the app still starts (the client is constructed with a placeholder)
  and the memory layers degrade to empty; recall/summary/graph need a real key.

### Startup dimension check (`src/app.py`)

When `VECTOR_MEMORY_ENABLED`, the lifespan reads `chat_memories.embedding`'s `atttypmod` (the pgvector
dimension) and warns loudly if it differs from `EMBEDDING_DIMENSION`. Switching to an embedder with a
different dimension requires `ALTER TABLE chat_memories ALTER COLUMN embedding TYPE vector(N)` and
re-embedding all rows.

### Feature flags (`src/conf.py`) and rollback safety

`SUMMARY_ENABLED`, `VECTOR_MEMORY_ENABLED`, and `GRAPH_MEMORY_ENABLED` (global, AND-ed with the
per-chat flags). `GRAPH_MEMORY_ENABLED` defaults **off** (it needs FalkorDB). With all three off,
`send_message` is byte-for-byte back-compatible (unit-tested:
`test_memory_flags_off_is_byte_identical_to_legacy`). The reminder and budgeting are gated on
`summary_enabled`, so they only activate when the summary layer can recover dropped history.

Key tunables: `MEMORY_SOURCE_TIMEOUT_MS` (800), `HISTORY_MAX_TAIL` (200), `DEFAULT_CONTEXT_LIMIT`
(32000), `SUMMARY_TRIGGER_TOKENS` (2000), `SUMMARY_FOLD_BATCH_TOKENS` (1000), `SUMMARY_TOKEN_CAP`
(500), `MEMORIES_TOKEN_CAP` (600), `MEMORIES_MAX_DISTANCE` (0.5), `MEMORIES_K` (5),
`MEMORIES_EF_SEARCH` (40), `REMINDER_TOKEN_CAP` (150).

---

## Layer 9 — Testing

- **Unit** (`tests/unit`, `@pytest.mark.unit`): `test_prompt_sections`, `test_budgeter`,
  `test_memory_service` (concurrent fan-out, per-source timeout → empty, per-chat flags, ingest
  idempotency + fault isolation, graph episode store, fact-vs-chunk dedup), `test_summary_service`
  (no-op under threshold, fold supersession, duplicate-swallow), `test_ingest_dispatcher` (own
  scope, swallows, uses REQUEST scope), `test_openai_embedder`, `test_openai_summary_model`,
  `test_vector_memory_gateway` (distance / exclude / dedup filters), `test_graphiti_memory_gateway`
  (episode store args, current-facts filter + cap, group-delete cypher). `test_chats_service` and
  `test_rabbit_llm` were updated for the new wiring, including the back-compat gate and graph
  cleanup on delete. **422 unit tests pass.**
- **E2E** (`tests/e2e/test_memory_api.py`, `@pytest.mark.e2e`): summary round-trip, context-usage
  breakdown, foreign-chat 403, and a 202 send with memory enabled (degrades gracefully without a
  key). Run against the live stack.
- **Eval** (`tests/eval/`, `@pytest.mark.eval`): scripted transcripts with probes (long-range
  callback today; reversal/multi-hop to follow), driven by `scripts/run_eval.py`. Skipped unless
  `EVAL_ENABLED=1` because they need the full stack + `OPENAI_API_KEY`.

---

## Known limitations / follow-ups

- **Graph memory is opt-in and unvalidated at scale.** `GRAPH_MEMORY_ENABLED` defaults off and needs
  FalkorDB + `OPENAI_API_KEY`. The plan's spike go/no-go (extraction quality + cost <\$0.002/turn)
  is still open — verify with the eval probes before relying on `[KNOWN FACTS]`.
- **`[MEMORIES]` turn attribution** is role-only (`[User]`/`[Character]`); a denormalised turn index
  is future polish.
- **`context-usage`** uses `""` as the vector query (the endpoint reports the budget structure, not
  exact recall for a specific follow-up).
- **Pre-existing, out of scope:** `append_model_message` does an unconditional INSERT, so a RabbitMQ
  redelivery duplicates the reply row. The Redis idempotency guard prevents a double-*ingest*, but
  the duplicate row itself is a separate issue.
