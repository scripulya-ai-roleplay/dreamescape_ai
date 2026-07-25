# Per-token response streaming

How the client sees the model's reply *token by token* as it is generated, instead of
getting one blob at the very end — and why that progress indicator can never corrupt,
duplicate, or replace the authoritative reply.

Like [AGENT_HANGING.md](./AGENT_HANGING.md), this doc is bottom-up: what the user sees →
the trick that delivers it → the code that implements it → the principle behind it.

> **Scope.** Streaming spans two apps: this backend (`scripulya_ai`) and the worker
> (`scripulya_agent`). The agent repo lives at `/home/h3ne58/scripulya_agent`. Paths below
> are prefixed with the repo name where it matters.

---

## 1. What the user sees, and what they don't

Without streaming, a chat reply is a single SSE event that arrives only after the whole
generation finishes:

```
client spinner: ⣾⣽⣻⢿⡿⣟⣯⣷   (spinning for 8s with no feedback)
                                              └─► event: message  {full reply}
```

With per-token streaming, the same 8s looks alive:

```
event: generation_start        ◄── "I'm thinking"
event: token   { "Hel"   }
event: token   { "lo"    }
event: token   { " world"}
event: generation_done         ◄── "the model finished talking"
event: message  { full reply }  ◄── the persisted, authoritative reply
```

A mid-stream failure ends the stream with a **different** terminal event, so the client can
tell the two apart *during* streaming — not only once the `message` arrives:

```
event: generation_start
event: token   { "Hel"   }
event: token   { "lo"    }
event: generation_error        ◄── "the stream failed before completing"
event: message  { FAILED/error reply }  ◄── the authoritative outcome (still arrives)
```

The crucial detail — and the whole design rests on it — is that **the token stream and the
final `message` are two independent channels.** The token stream is *decorative*: it is a
progress animation and nothing more. The `message` event is *authoritative*: it is the real,
persisted reply, and it is produced by a completely separate path that streaming never
touches.

---

## 2. The big picture: one generation, two channels

A single generation flows over **two parallel transports**, correlated by the same
`request_id`:

```
   scripulya_ai (backend)                          scripulya_agent (worker)
   ────────────────────                          ──────────────────────────

   POST /messages  ─► 202
        │
        ▼
   ScripulyaAgentClient.publish
        │
        ├──► RabbitMQ "llm.agent.request"  ─────►  handle_llm_request
        │      (correlation_id = request_id)            │
        │                                               ▼
        │                                         provider gateway streams
        │                                         from the LLM SDK
        │                                               │
        │   ◄── Redis PUBLISH gen:{rid}:tokens  ◄───────┤  (per delta)
        │           {"type":"token","text":...}         │
        │                                               │
        │                                         finally: PUBLISH {"type":"done"}
        │
        ├──► _start_token_relay  (subscribes to gen:{rid}:tokens)
        │         │
        │         ▼  drains + batches tokens
        │   ChatEventGateway.publish_token  ──► SSE queue ──► GET /chats/{id}/events
        │
        └──► (fire-and-forget; publish returns immediately)

   ............ separate, slower, authoritative channel ............
   RabbitMQ "llm.agent.result"  ◄────────────  @router.publisher(result queue)
        │
        ▼
   handle_agent_result
        ├── MessageService.append_model_message   (DB write — the real reply)
        └── ChatEventGateway.publish_message     ─► SSE queue ─►  event: message
```

- **Top path (Redis pub/sub):** fast, per-delta, decorative. Drives the spinner.
- **Bottom path (RabbitMQ result queue):** once, after generation, authoritative. Drives
  the persisted message and the `message` SSE event.

Both publish into the *same* in-memory `ChatEventGateway`, so the single SSE stream the
client holds receives both interleaved.

---

## 3. The correlation key: `request_id`

Everything keys off one UUID, generated **by the backend** at publish time:

```python
# scripulya_ai: src/infrastructure/gateways/scripulya_agent_gateway.py
request_id = uuid4()
await self.broker.publish(req.model_dump(mode="json"), self.request_queue,
                          correlation_id=str(request_id), timeout=self.timeout)
```

It is sent as the **RabbitMQ `correlation_id`**. The agent reads that same value back and
reuses it everywhere:

```python
# scripulya_agent: src/controllers/llm.py
CorrelationId = Annotated[str, Context("message.correlation_id", default="")]
...
channel = tokens_key(correlation_id) if correlation_id else ""   # gen:{rid}:tokens
```

So one `request_id` ties together, for one generation:

| Use | Key / field | Owner |
|---|---|---|
| RabbitMQ request correlation | `correlation_id` header | backend sets, agent reads |
| Liveness chalkboard | `gen:{rid}:alive`, `:done`, `:chat` | heartbeat/watchdog (see AGENT_HANGING.md) |
| **Token stream channel** | `gen:{rid}:tokens` | **this doc** |

This is why streaming is correlated to *the right generation*, not just the chat. A chat can
have several generations in flight; each gets its own token channel, and the SSE frames carry
the `request_id` so the client can attribute each token batch.

---

## 4. The cast

```
   scripulya_ai (backend)
   ────────────────────
   ScripulyaAgentClient.publish          publish + start relay (APP-scoped singleton)
     └─ _start_token_relay               subscribe to gen:{rid}:tokens, spawn _drain_tokens
     └─ _drain_tokens                    batch + flush frames → events gateway
   ChatEventGateway                      in-memory fan-out: chat_id → set[Queue] (APP singleton)
   ServerEventsService._stream           one SSE response; subscribes a queue, emits frames
   handle_agent_result                   RabbitMQ result consumer → publish_message (authoritative)

   scripulya_agent (worker)
   ──────────────────────────
   handle_llm_request                    subscriber; builds _emit, runs Heartbeat + timeout
   AgentService.handle                   routes model → provider service, threads on_token
   {Anthropic,Zai,Google,...}Gateway     streams from SDK, calls emit_token per delta
   _streaming.emit_token                 swallows errors; forwards a delta to _emit
   _close_token_stream                   finally: publishes {"type":"done"|"error"}
```

---

## 5. The frame contract (Redis pub/sub on `gen:{rid}:tokens`)

This is the wire format on the Redis channel — a **contract shared with the agent**, like
the heartbeat keys. The agent `PUBLISH`es JSON strings; the backend parses them. (Why a
Pub/Sub channel rather than a Stream or List is a deliberate choice — see §14.)

```jsonc
{"type": "token", "text": "<delta>"}   // one per generated text chunk
{"type": "done"}                        // terminal: generation completed
{"type": "error"}                       // terminal: timeout or provider error
```

Only three frame types. `text` is present only on `token`. A terminal frame (`done`/`error`)
is what tells the backend relay to stop draining. The two terminals are **not** symmetric on
the wire: `done` maps to an SSE `generation_done`; `error` (or any end that isn't a clean
`done`) maps to `generation_error` — see §6e and §8.

---

## 6. Step by step

### 6a. Backend publishes the request and opens the relay

`ScripulyaAgentGateway.submit` is fire-and-forget — it returns `None` so the caller leaves
the placeholder message `PENDING`. The real reply comes back later via RabbitMQ. Inside
`submit`, it calls `ScripulyaAgentClient.publish`, which runs four steps **in order**:

1. **subscribe** — `await self._subscribe_tokens(rid)` opens and awaits the Redis subscription
   to `gen:{rid}:tokens` **before** the request is published.
2. **publish** — `broker.publish(..., correlation_id=rid)`; if it raises, the subscription
   from step 1 is closed and the error propagates (no relay spawned, no liveness armed).
3. **arm liveness** — `heartbeat.register_inflight(rid, chat_id)`, only after publish succeeds
   (a failed publish is already surfaced by `send_message`, and a leftover entry here would be
   FAILed again by the watchdog).
4. **drain** — `create_task(self._drain_tokens(pubsub, rid, chat_id))`, only if step 1 returned
   a real pubsub; the task is tracked in `self._relays` and auto-discarded on completion.

The **subscribe-before-publish** order is load-bearing: Pub/Sub delivers only to clients
subscribed at the instant of `PUBLISH`, and the agent can emit its first token the moment it
receives the request — so subscribing first is the only way to guarantee no opening frame (or
the terminal `done`/`error` frame) is missed. Frames that arrive between subscribe-completion
and the drain task starting are buffered in the connection's TCP socket and read on the first
`get_message`. (The transport choice itself — Pub/Sub over Stream/List — is deliberate; see
§14.) If `redis`/`events` aren't wired (e.g. mock mode), `_subscribe_tokens` returns `None` and
steps 2–3 still run — streaming silently off, generation unaffected.

### 6b. Agent generates and emits deltas

`handle_llm_request` (subscriber on `llm.agent.request`) builds a tiny closure and threads it
all the way down to the provider SDK:

```python
channel = tokens_key(correlation_id) if correlation_id else ""

async def _emit(text: str) -> None:
    if not channel or not text:
        return
    await redis_client.publish(channel, json.dumps({"type": "token", "text": text}))

async with Heartbeat(redis_client, correlation_id):
    async with asyncio.timeout(settings.LLM_GENERATION_TIMEOUT_SECONDS):
        reply = await svc.handle(msg, on_token=_emit)
```

`AgentService.handle` routes `request.message.llm_model` → provider service → gateway
`generate(..., on_token=_emit)`. Each gateway streams from its SDK and calls
`await emit_token(on_token, delta)` per delta. `emit_token` swallows any error — **a Redis
blip must never abort the generation** (streaming is decorative; mirrors the heartbeat's
best-effort philosophy).

### 6c. Per-provider streaming idioms

Every provider exposes a different async-streaming shape; the gateways paper over it:

| Provider | SDK call | Iterate | Delta accessor |
|---|---|---|---|
| **Anthropic** | `client.messages.stream(...)` (context mgr) | `async for delta in stream.text_stream` | `delta` (already text) |
| **OpenAI-compat** (Z.ai, DeepSeek) | `chat.completions.create(..., stream=True)` | `async for chunk in stream` | `chunk.choices[0].delta.content` |
| **Google** | `await client.aio.models.generate_content_stream(...)` | `async for chunk in stream` | `chunk.text` |

Two subtleties worth calling out:

- **Google's stream is `async def`** — it must be `await`ed to get the async iterator (the
  `await` performs the HTTP connection setup). Forgetting the `await` iterates a coroutine,
  not chunks.
- **OpenAI-compat streaming sends `usage=None`.** `stream_options` is omitted because
  third-party OpenAI-compatible servers may reject it, so usage is unavailable on the
  streaming path (it was only ever used for logging). The non-streaming shape keeps usage.

Each gateway also accumulates the full text locally (`parts`/`buffer`) so the authoritative
`LLMResponse.text` is reconstructed from the gateway's own accumulation — **not** from the
Redis token stream. The two text sources are independent; the relay is not a source of truth.

### 6d. Agent closes the stream

In `handle_llm_request`'s `finally`, regardless of outcome:

```python
await _close_token_stream(redis_client, channel, outcome)   # {"type":"done"} or {"type":"error"}
await mark_done(redis_client, correlation_id)               # liveness (see AGENT_HANGING.md)
```

`outcome` is `"done"` on success, `"error"` on timeout or provider exception. This terminal
frame is what lets the backend relay stop.

### 6e. Backend relays frames into SSE events

`_drain_tokens` turns the firehose of Redis frames into a measured trickle of SSE events.
It emits `generation_start` immediately, then loops until either a terminal frame arrives or
a hard deadline elapses:

```python
self.events.publish_generation_start(chat_id, UUID(request_id))   # immediately
deadline = loop.time() + settings.LLM_HEARTBEAT_HARD_DEADLINE_SECONDS   # 1800s backstop
buffer, last_flush = [], loop.time()
terminal = None                                     # "done" is the only clean outcome
while loop.time() <= deadline:
    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=_FLUSH_INTERVAL_SECONDS)  # 25ms
    if msg is None:                                  # no frame this tick
        if buffer and loop.time()-last_flush >= _FLUSH_INTERVAL_SECONDS:
            self._flush(buffer, ...); buffer=[]; last_flush=loop.time()
        continue
    frame = json.loads(msg["data"])
    if frame["type"] == "token":
        buffer.append(frame.get("text",""))
        if len(buffer) >= _FLUSH_TOKEN_BATCH or loop.time()-last_flush >= _FLUSH_INTERVAL_SECONDS:
            self._flush(buffer, ...); buffer=[]; last_flush=loop.time()
    elif frame["type"] in ("done","error"):
        terminal = frame["type"]; break
# finally: flush any tail, then
if terminal == "done":
    self.events.publish_generation_done(chat_id, UUID(request_id))
else:                                               # "error" frame, deadline expiry, or relay crash
    self.events.publish_generation_error(chat_id, UUID(request_id))
```

`_flush` joins the buffered strings and calls `events.publish_token(chat_id, request_id, text)`
(no-op if empty). So the client gets, per generation:

```
success:  generation_start → token → … → token → generation_done
failure:  generation_start → token → … → token → generation_error
```

A clean `done` is the *only* thing that earns `generation_done`. An `error` frame, a deadline
expiry (no terminal frame — the agent crashed or the frame was lost), or a relay crash all
yield `generation_error`. The partial text is flushed either way; the terminal event tells the
client what to make of it.

### 6f. Backend fans out to the SSE stream

`ChatEventGateway` is an APP-scoped singleton holding `dict[chat_id, set[Queue]]`. The token
relay (also APP-scoped) and each SSE request share this one instance:

```python
def publish_token(self, chat_id, request_id, text):
    self.publish(chat_id, {"_sse_event": "token", "request_id": str(request_id), "text": text})
```

`publish` is `put_nowait` into every subscribed queue — non-blocking, drops on `QueueFull`
(bounded at 256 so a stalled client can't exhaust memory). `ServerEventsService._stream`
subscribed one such queue when the client opened `GET /chats/{id}/events`; it drains that
queue and emits each event as an SSE frame.

---

## 7. The batching trick (why not one SSE event per token?)

LLMs emit deltas fast — often hundreds per second for some providers. Emitting one SSE frame
per delta would flood the client and the network for little perceptible gain. The relay
**coalesces** deltas with two triggers, whichever fires first:

| Trigger | Constant | Effect |
|---|---|---|
| batch size | `_FLUSH_TOKEN_BATCH = 16` | flush once 16 deltas accumulate |
| time | `_FLUSH_INTERVAL_SECONDS = 0.025` (25ms) | flush if 25ms passed since the last flush |

25ms is below the human perception threshold for "live" text (~40fps), so the output still
*reads* as streaming, while the SSE frame count drops by an order of magnitude. The same 25ms
timeout is reused as the `pubsub.get_message` poll interval, so an idle period flushes the
tail without a separate timer.

---

## 8. The SSE wire format

`ServerEventsService._sse_frame` peels the synthetic `_sse_event` key out of the payload to
use as the SSE `event:` name; everything else becomes the JSON `data:` body:

```python
def _sse_frame(self, payload):
    event_name = payload.get("_sse_event", "message")
    data = {k: v for k, v in payload.items() if k != "_sse_event"}
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
```

So a **successful** generation produces, on the wire:

```
event: generation_start
data: {"request_id": "11111111-2222-3333-4444-555555555555"}

event: token
data: {"request_id": "11111111-2222-3333-4444-555555555555", "text": "Hello world"}

event: generation_done
data: {"request_id": "11111111-2222-3333-4444-555555555555"}

event: message
data: {"message": { …full persisted model message… }}
```

A **failed** generation is identical up to the terminal event, which is `generation_error`
instead of `generation_done`:

```
event: generation_start
data: {"request_id": "11111111-2222-3333-4444-555555555555"}

event: token
data: {"request_id": "11111111-2222-3333-4444-555555555555", "text": "Hel"}

event: generation_error
data: {"request_id": "11111111-2222-3333-4444-555555555555"}

event: message
data: {"message": { …FAILED / error reply… }}
```

Notes for a client implementer:

- **Attribute tokens by `request_id`.** If the user fires two messages quickly, two
  generations' token frames can interleave on the same chat stream; `request_id` separates
  them.
- **The terminal event tells you success vs failure.** `generation_done` means the stream
  completed cleanly; `generation_error` means it ended abnormally (provider error, timeout, or
  the relay/agent dying). They are mutually exclusive — a generation emits exactly one. Either
  way the authoritative outcome is the later `message` event; the terminal events are
  best-effort stream signals, not the reply. Don't render the streamed tokens as final text —
  wait for `message`.
- **Reconnect replays state, not tokens.** On connect, `_stream` emits the latest persisted
  model message first (so a reconnecting client isn't blank). Tokens are ephemeral — a
  reconnect mid-generation will *not* replay the deltas already streamed; the client just
  gets the eventual `message`.
- A comment frame `: keepalive\n\n` is sent every 15s of idleness to keep the connection
  alive through proxies.

---

## 9. Why streaming can never break a generation (the decorative guarantee)

Every component on the token path treats Redis as best-effort and isolates failures:

| Failure | Agent side | Backend side | Net effect |
|---|---|---|---|
| Redis down at publish | `emit_token` swallows the error; generation continues | `_subscribe_tokens` returns `None` (or subscribe fails → logs + returns) | no live tokens, but reply still arrives via RabbitMQ |
| Redis dies mid-stream | `_close_token_stream` swallows the publish error | `get_message`/`json.loads` errors are caught per-frame; loop continues until deadline | tokens stop early; `generation_error` fires at the deadline |
| Agent crashes (no `done`) | — | deadline (`LLM_HEARTBEAT_HARD_DEADLINE_SECONDS`, 1800s) elapses with no terminal → `generation_error` in `finally` | spinner stops; watchdog writes the FAILED reply (see §10) |
| No SSE listener / queue full | — | `publish` no-ops or drops on `QueueFull` (logged) | tokens silently dropped; generation unaffected |
| Mock mode (`LLM_AGENT_ENABLED=false`) | n/a | `MockScripulyaAgentClient` — no broker, no relay | no streaming; `testing_mock` still works offline |

The load-bearing invariant: **the persisted reply is created only by the RabbitMQ result
consumer** (`handle_agent_result` → `MessageService.append_model_message` →
`publish_message`). The relay never writes to the database, never constructs a message, never
emits a `message` event. Strip the entire token path out and the chat still works — it just
stops showing live progress. That is the definition of "decorative."

Symmetrically, the agent reconstructs `LLMResponse.text` from its **own** accumulation in the
gateway, never from the Redis stream — so even a total relay failure leaves the authoritative
reply intact.

---

## 10. Relation to the anti-hang system

Streaming reuses two pieces of the heartbeat/watchdog machinery from
[AGENT_HANGING.md](./AGENT_HANGING.md):

1. **The same `request_id`.** The token channel is `gen:{rid}:tokens`, a sibling of the
   liveness keys `gen:{rid}:{alive,done,chat}`. One id correlates the RabbitMQ request, the
   liveness chalkboard, *and* the token stream.

2. **The same hard-deadline backstop.** The relay's deadline is
   `settings.LLM_HEARTBEAT_HARD_DEADLINE_SECONDS` (1800s) — the very value the heartbeat uses
   as the TTL on `gen:{rid}:chat`. So if the agent dies and never sends `done`/`error`, the
   relay self-terminates after the backstop and emits `generation_error`, so the client's
   spinner can't spin forever *on its own*.

But note the two systems act on **different outcomes**:

```
dead agent  ─►  heartbeat :alive expires  ─►  watchdog writes FAILED message   (≤ ~40s)
                                                + SSE event: message (FAILED)

dead agent  ─►  relay deadline elapses      ─►  SSE event: generation_error      (≤ 1800s)
                                                (stream ended abnormally; spinner stops)
```

The watchdog owns the *authoritative* failure (a real `FAILED` row + `message` event). The
relay only owns the *decorative* "stop animating" signal. They are independent safety nets:
either can fire without the other, and neither duplicates the other's job.

---

## 11. Edge cases & limitations

| Case | Behavior |
|---|---|
| **Redis unavailable** | Relay never starts (or dies silently); agent `emit_token` swallows errors. Reply still arrives via RabbitMQ. |
| **Terminal frame never sent** (agent crash) | Relay runs to the 1800s deadline, then flushes tail + emits `generation_error`. Watchdog separately FAILs the generation. |
| **`error` terminal** | Relay flushes any buffered tokens first (so partial output isn't lost), then emits `generation_error`. The provider error itself reaches the user as a `FAILED`/error `message` via the result queue. |
| **Client reconnects mid-generation** | Latest persisted message is replayed; in-flight tokens are *not* replayed. Client sees the eventual `message`. |
| **Slow/stalled SSE client** | Per-listener queue capped at 256; overflow drops token events (logged). Generation unaffected. `message` events can also be dropped — a stalled client may miss the reply over SSE and must refetch. |
| **Multiple generations on one chat** | Each has its own `request_id`; frames are distinguishable. The client is expected to bucket by `request_id`. |
| **Relay task lifetime** | Tracked in `_relays` and auto-discarded on completion; not awaited on shutdown (best-effort). |
| **Terminal (`generation_done`/`generation_error`) vs `message`** | Normally the terminal event precedes `message` (the result round-trips through RabbitMQ + a DB write after generation). They are decoupled channels — key off `message` for the authoritative outcome. Rare mismatch: if the relay itself crashes mid-stream it emits `generation_error` even though the agent may still succeed and deliver a normal `message` — trust the `message`. |

---

## 12. Configuration & constants

There is no dedicated settings block for streaming; it reuses heartbeat/SSE knobs plus a few
module-level constants.

**Backend constants** (`src/infrastructure/gateways/scripulya_agent_gateway.py`):

```
_FLUSH_INTERVAL_SECONDS = 0.025   # pubsub poll interval AND max token-batch latency
_FLUSH_TOKEN_BATCH      = 16      # max deltas coalesced per SSE token event
```

**SSE constants** (`src/application/events/server_events_service.py`,
`src/infrastructure/gateways/chat_event_gateway.py`):

```
_KEEPALIVE_SECONDS = 15.0         # idle SSE comment-frame interval
_LISTENER_MAXSIZE  = 256          # per-listener queue cap (backpressure)
```

**Shared setting** (`src/conf.py`, also used by the heartbeat):

```
LLM_HEARTBEAT_HARD_DEADLINE_SECONDS = 1800   # relay deadline = backstop for a missing terminal frame
```

**Agent** (`scripulya_agent/src/controllers/llm.py`): no streaming-specific config; it rides
on `LLM_GENERATION_TIMEOUT_SECONDS` (the provider-call hard cap that bounds how long the
stream can run before an `error` terminal).

> **Cross-repo contract.** The channel name `gen:{rid}:tokens` and the three frame types
> (`token`/`done`/`error`) are shared with `scripulya_agent`. There is no shared package —
> keep them in sync manually, same as the heartbeat keys.

---

## 13. File map

**Backend — `scripulya_ai`**

```
src/infrastructure/gateways/scripulya_agent_gateway.py   ScripulyaAgentClient: publish, _start_token_relay,
                                                          _drain_tokens (batch+flush), _flush
src/infrastructure/gateways/chat_event_gateway.py        ChatEventGateway: publish_token / publish_generation_start / _done
src/application/ports/chats.py                           IChatEventGateway (port): the three publish_* methods
src/application/events/server_events_service.py          _sse_frame: _sse_event → event: name; _stream SSE generator
src/controllers/api/v1/chat_events.py                    GET /api/v1/chats/{id}/events  (the SSE endpoint)
src/controllers/rabbit/v1/llm.py                         handle_agent_result: authoritative message-create + publish_message
src/infrastructure/gateways/redis_heartbeat.py           tokens_key(rid) = "gen:{rid}:tokens"  (shared contract)
src/infrastructure/di.py                                 wires redis + events into ScripulyaAgentClient (both APP-scoped)
tests/unit/test_scripulya_agent_gateway.py               TestTokenRelay: start/skip relay, drain+batch, error-terminal flush
tests/unit/test_chat_event_gateway.py                    publish_token / generation_start / generation_done / generation_error
```

**Agent — `scripulya_agent`**

```
src/controllers/llm.py                                   handle_llm_request: _emit, _close_token_stream, finally
src/application/agent/service.py                         AgentService.handle: threads on_token to the provider gateway
src/infrastructure/gateways/_streaming.py                emit_token: error-swallowing delta forwarder
src/infrastructure/gateways/anthropic_gateway.py         messages.stream + text_stream
src/infrastructure/gateways/{zai,deepseek}_gateway.py    chat.completions.create(stream=True); usage=None
src/infrastructure/gateways/google_gateway.py            await generate_content_stream(...) + async for
src/infrastructure/heartbeat.py                          tokens_key(rid)  (shared contract)
```

---

## 14. Why Redis Pub/Sub (and not Streams or Lists)

The token channel is a Redis **Pub/Sub** channel, not a Stream or a List. That is deliberate,
and it follows directly from §9: the token stream is *decorative and ephemeral*, so the right
transport is one that retains **nothing**.

Pub/Sub is pure fan-out with zero retained state. A `PUBLISH` reaches only clients subscribed
at that instant; Redis holds the message only in the live output buffers of connected
subscribers, and the channel key is never materialized. When the generation ends there is
nothing to clean up — no key, no entries, no TTL to set. For a fire-and-forget progress signal
that is *supposed* to vanish, that is the ideal property, not a limitation.

The persistence that Streams (`XADD`/`XREAD`) or Lists (`RPUSH`/`BLPOP`) add is only worth
paying for if the design *uses* it. This one deliberately does not:

| Capability persistence buys | Used here? | Why |
|---|---|---|
| Replay/resume after the relay restarts mid-generation | No | Tokens are decorative; the authoritative reply still arrives via RabbitMQ → DB → `message` (§9). A lost prefix is invisible. |
| Client reconnect resuming the in-flight stream | No, by design | Reconnect replays the latest persisted `message`, not ephemeral deltas (§8, §11). |
| Multi-consumer fan-out / per-consumer ack | No | Exactly one relay consumer per generation. |

and it comes with real costs:

|  | Pub/Sub | List | Stream |
|---|---|---|---|
| Retained state | none | grows until trimmed | bounded via `MAXLEN` |
| Cleanup per generation | none | must `DEL` / `EXPIRE` | must `DEL` / `EXPIRE` the key |
| Multi-consumer fan-out | all subscribers | one consumer per frame (queue) | consumer groups / N readers |
| Replay / resume | none | manual cursor | native (`XREAD` from an ID) |
| Per-frame overhead | lowest | `RPUSH` | `XADD` (heaviest) |

So Stream/List would add cleanup bookkeeping and heavier writes for a retention capability
that is unused. **A List is a poor fit in either world** — no clean fan-out, awkward replay,
manual trimming — so if persistence ever *were* wanted, it would be Stream, not List.

### The one constraint Pub/Sub imposes (and how it's met)

"Deliver only to subscribers present at PUBLISH time" means the relay must be subscribed before
the agent can emit. Since the agent can emit only after it receives the RabbitMQ message,
`publish` subscribes before publishing (§6a) — the race is closed by **ordering**, not by
retention.

### When this choice would change

Pub/Sub stays correct as long as the relay and the SSE client are co-located in one backend
process. Note there are **two hops**: the agent→relay channel (hop 1, Redis) is separate from
the relay→SSE fan-out (hop 2, the in-memory `ChatEventGateway`, which is per-process — §4). The
day the backend runs **multiple replicas**, hop 2 breaks token delivery regardless of hop 1's
transport: the SSE request lands on a different replica than the relay task, and the in-memory
queue never crosses the process boundary. Fixing *that* means backing hop 2 with Redis too —
and then a **Stream** (fan-out + resume + auto-trim) is the right tool where Pub/Sub (fan-out
only) sufficed for one replica. That is a future requirement; today it is premature.

---

## 15. The principle

Streaming is a **second, decorative channel layered over an unchanged authoritative one.**

```
authoritative path (RabbitMQ result → DB → event: message)   ── UNCHANGED, source of truth
decorative path   (Redis pub/sub → relay → event: token)     ── ADDED, best-effort, removable
```

Three properties make that safe:

- **Correlation without coupling.** Both channels key off the one `request_id` the backend
  mints, so they describe the same generation — but neither path calls into the other.
- **Best-effort end to end.** Every Redis touch on the token path (agent `emit_token`,
  `_close_token_stream`; backend subscribe, `get_message`, `json.loads`, flush) swallows its
  own errors. A failure anywhere only degrades the animation.
- **The relay never holds truth.** It emits only `generation_start` / `token` /
  `generation_done` / `generation_error`. The persisted reply comes solely from the RabbitMQ
  result consumer. The
  agent's authoritative text comes solely from its own gateway accumulation. The token stream
  is a mirror, never a source.

The batching (16 deltas / 25ms) is the one optimization that matters: it keeps the stream
*feeling* live while collapsing the SSE frame count — and it lives entirely inside the relay,
invisible to both the agent and the client.
