# Atlas Cortex — Memory System (HOT/COLD Architecture)

> Adapted from the [agentic-memory-quest](https://github.com/Betanu701/agentic-memory-quest/blob/copilot/add-hot-cold-memory-architecture/docs/memory-architecture.md) HOT/COLD design, fully localized for self-hosted infrastructure.

## Overview

Atlas Cortex has a **shared memory layer** with two independent paths, entirely local:

| Path | Direction | Latency Target | Blocking? | Infrastructure |
|------|-----------|----------------|-----------|----------------|
| **HOT** | Read-only retrieval | Sub-50ms | Synchronous during request | ChromaDB + SQLite FTS5 |
| **COLD** | Async ingestion | Best-effort | Non-blocking (fire-and-forget) | Python asyncio queue |

Memory is integrated into **every processing layer** — Layer 0 loads context, Layer 1 uses it for personalized instant answers, Layer 2 uses it for device preferences, and Layer 3 injects it into the LLM prompt.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Message                                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
                 ┌─────────────────┐
                 │  Atlas Cortex   │
                 │  Pipe Function  │
                 └────┬───────┬────┘
                      │       │
         ┌────────────┘       └──────────────┐
         ▼                                   ▼
 ┌───────────────┐                  ┌────────────────┐
 │   HOT PATH    │                  │   COLD PATH    │
 │  (retrieve)   │                  │ (enqueue_write) │
 │  Read-only    │                  │  Fire-and-forget│
 └───────┬───────┘                  └───────┬────────┘
         │                                  │
         ▼                                  ▼
 ┌───────────────────┐             ┌────────────────────┐
 │  Query Embedding   │             │  asyncio.Queue     │
 │  (Ollama embed)    │             │  (in-process)      │
 └───────┬───────────┘             └───────┬────────────┘
         │                                 │
         ▼                                 ▼
 ┌───────────────────┐            ┌────────────────────┐
 │  Hybrid Retrieval  │            │  PII Redactor       │
 │  ┌──────┐ ┌─────┐ │            │  (regex rules)      │
 │  │ FTS5 │ │Chroma│ │            └───────┬────────────┘
 │  │(BM25)│ │(vec) │ │                    │
 │  └──┬───┘ └──┬──┘ │                    ▼
 │     └──┬─────┘    │            ┌────────────────────┐
 │        ▼          │            │  Memory Decider     │
 │   RRF Fusion      │            │  (heuristics +      │
 │   (k=60)          │            │   optional LLM)     │
 └───────┬───────────┘            └───────┬────────────┘
         │                                │
         ▼                                ▼
 ┌───────────────────┐            ┌────────────────────┐
 │  Cross-Encoder     │            │  Embedder           │
 │  Reranker          │            │  (Ollama embed)     │
 │  (optional, local) │            └───────┬────────────┘
 └───────┬───────────┘                     │
         │                                 ▼
         ▼                        ┌────────────────────┐
 ┌───────────────────┐            │  Upsert to ChromaDB │
 │  Top-K MemoryHits  │            │  (idempotent)       │
 │  → Context Assembly│            └────────────────────┘
 └────────────────────┘
```

---

## Local Technology Mapping

Replacing every cloud service with a local equivalent:

| Original (Azure) | Local Replacement | Notes |
|-------------------|-------------------|-------|
| Azure OpenAI embeddings | **Ollama** `nomic-embed-text` | 768-dim, runs on CPU, ~5ms/embed |
| Azure AI Search (vector) | **ChromaDB** | Embedded mode, HNSW index, Python-native |
| Azure AI Search (BM25) | **SQLite FTS5** | Built into Python's sqlite3, sub-ms queries |
| Event Hubs | **asyncio.Queue** | In-process, zero latency, no external dependency |
| Semantic Ranker | **Cross-encoder** (optional) | `cross-encoder/ms-marco-MiniLM-L-6-v2` via sentence-transformers, CPU |
| Azure Monitor | **SQLite metrics tables** | Query locally, optional Grafana export |

### Why ChromaDB?

- **Embedded mode** — runs in-process, no separate container needed
- **Persistent storage** — SQLite backend, survives restarts
- **Built-in embedding** — but we'll use Ollama's for consistency
- **Metadata filtering** — `where={"user_id": "derek", "type": "preference"}`
- **Lightweight** — ~50MB RAM for thousands of documents
- **Open source** — Apache 2.0

### Why Ollama for Embeddings?

Ollama already runs on the server. Embedding models are tiny and share the GPU:

| Model | Dims | Size | Speed (CPU) |
|-------|------|------|-------------|
| `nomic-embed-text` | 768 | 274MB | ~5ms/embed |
| `all-minilm` | 384 | 46MB | ~2ms/embed |
| `mxbai-embed-large` | 1024 | 670MB | ~8ms/embed |

**Recommendation:** `nomic-embed-text` — best balance of quality and speed, runs entirely on CPU leaving GPU free for LLM.

---

## HOT Path (Reads)

### Flow

1. **Compute query embedding** using Ollama (`nomic-embed-text`)
2. **Sparse search**: SQLite FTS5 text retrieval (BM25 scoring)
3. **Dense search**: ChromaDB vector similarity (cosine via HNSW)
4. **RRF Fusion**: Combine ranked lists using Reciprocal Rank Fusion (`score = Σ 1/(k + rank_i)`, `k=60`)
5. **Reranker** (optional): Local cross-encoder for final ordering
6. Return top-K (`MEMORY_K`, default 8) `MemoryHit` objects

### Constraints

- **No writes** — the hot path is strictly read-only
- **Sub-50ms** retrieval budget (faster than Azure since everything is local)
- **Fallback on failure** — returns empty context (never fails the request)
- **Feature flags**: `MEMORY_ENABLED`, `HOT_RETRIEVAL_ENABLED`

### User Isolation

All queries filter by `user_id`. In multi-user scenarios:
- Typed messages: user_id from Open WebUI session
- Voice messages: user_id from speaker identification
- Unknown speaker: query against "shared" memory only (house rules, device states)

---

## COLD Path (Writes)

### Pipeline Stages

```
Interaction Complete
         ↓
  enqueue_write(MemoryEvent)
         ↓
  ┌──────────────┐
  │ PII Redactor  │ → mask/drop sensitive data (regex-based)
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ Memory Decider│ → drop low-signal chit-chat; keep preferences, facts, decisions
  └──────┬───────┘    dedup via content hash; TTL for volatile items
         ▼
  ┌──────────────┐
  │   Embedder    │ → Ollama nomic-embed-text (batched, cached by content hash)
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │   Upserter    │ → idempotent upsert to ChromaDB + FTS5 mirror
  └──────────────┘
```

### Memory Decider — What Gets Stored

The decider runs heuristics first (fast), with optional LLM assist for ambiguous cases:

| Signal | Action | Example |
|--------|--------|---------|
| Stated preference | **STORE** (type: preference) | "I like the lights at 40%" |
| Personal fact | **STORE** (type: fact) | "My birthday is March 15" |
| Decision/choice | **STORE** (type: decision) | "Let's use PostgreSQL for that" |
| Correction | **STORE** (type: correction, links to original) | "Actually I meant the bedroom, not bathroom" |
| Emotional state | **STORE** (type: mood, TTL: 24h) | "I'm so frustrated with this" |
| Chit-chat/filler | **DROP** | "haha", "ok", "thanks" |
| Repeated info | **DEDUP** (bump timestamp) | Same preference stated again |
| Question only | **DROP** (unless reveals intent) | "What time is it?" |

### Append-Only Design

**Critical**: Memory is never overwritten, only appended. When a correction occurs:

```
Memory #1: { text: "Derek's favorite color is blue", type: "fact", ts: "2026-02-15" }
Memory #2: { text: "Derek's favorite color is green (corrected from blue)", 
             type: "correction", supersedes: "#1", ts: "2026-03-01" }
```

The HOT path always prefers the latest entry when conflicts exist (sorted by timestamp, corrections ranked higher).

### PII Redaction

Local-only, regex-based:

| Pattern | Action |
|---------|--------|
| Email addresses | Mask: `[EMAIL]` |
| Phone numbers | Mask: `[PHONE]` |
| SSN-like patterns | Mask: `[SSN]` |
| Credit card numbers | Mask: `[CC]` |
| IP addresses | Keep (useful for home network context) |
| Names | Keep (essential for personalization) |

---

## ChromaDB Collection Schema

**Collection name**: `cortex_memory`

```python
{
    "id": "sha256(user_id|type|ts|content_hash)",  # deterministic, idempotent
    "embedding": [0.123, -0.456, ...],              # 768-dim from nomic-embed-text
    "document": "Derek prefers lights at 40% in the evening",  # searchable text
    "metadata": {
        "user_id": "derek",
        "type": "preference",           # preference, fact, decision, correction, mood, interaction
        "source": "conversation",        # conversation, onboarding, nightly_evolution, system
        "tags": ["lighting", "evening", "preference"],
        "supersedes": null,              # ID of memory this corrects (null if original)
        "ttl": null,                     # ISO timestamp for expiry (null = permanent)
        "confidence": 0.9,              # how confident we are this is accurate
        "created_at": "2026-02-27T06:00:00Z",
        "interaction_id": 42            # links back to interaction that spawned this
    }
}
```

### FTS5 Mirror Table (for BM25 sparse search)

```sql
CREATE VIRTUAL TABLE memory_fts USING fts5(
    doc_id,          -- matches ChromaDB id
    user_id,
    text,            -- searchable content
    type,            -- preference, fact, decision, etc.
    tags,            -- space-separated for FTS matching
    tokenize='porter unicode61'
);
```

---

## Memory-Aware Processing

### How Memory Flows Through Layers

```
Layer 0 (Context Assembly):
  HOT query: retrieve top-K memories for this user
  Result: [
    "Derek prefers lights at 40% in evening",
    "Derek is a night owl, usually active 9-11 PM",
    "Derek gets frustrated with slow responses",
    "Derek has a daughter named Emma (age 4)",
  ]
  → Injected into all subsequent layers

Layer 1 (Instant Answers):
  User: "What's my daughter's name?"
  Memory hit: "Derek has a daughter named Emma (age 4)"
  → Instant answer: "Emma! She's 4, right?" (no LLM needed)

Layer 2 (Device Commands):
  User: "Set the lights for evening"
  Memory hit: "Derek prefers lights at 40% in evening"
  → light.living_room.set_brightness(40) (personalized default)

Layer 3 (LLM):
  System prompt includes:
  "[MEMORY CONTEXT]
   - Derek prefers lights at 40% in evening
   - Derek is a night owl
   - Derek has a daughter Emma (age 4)
   [END MEMORY CONTEXT]"
  → LLM response is naturally personalized
```

---

## Integration with Existing Systems

### Open WebUI Memory Tool
The existing Memory Manager tool in Open WebUI stores simple key-value pairs. Cortex memory **replaces** this with a much richer system:
- Vector search vs exact key match
- Hybrid retrieval (BM25 + vector) vs single lookup
- Automatic memory extraction vs manual save commands
- Per-user emotional profiles vs flat storage

### Nightly Evolution Job
The evolution job (Phase C2) feeds the COLD path:
- New device patterns → stored as system memories
- User behavior patterns → stored as behavioral facts
- Emotional profile updates → stored as personality memories

---

## Observability

Since everything is local, observability is SQLite-based:

```sql
CREATE TABLE memory_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operation TEXT,         -- 'hot_retrieve' | 'cold_ingest' | 'cold_decide' | 'cold_embed'
    latency_ms REAL,
    hit_count INTEGER,      -- number of results (for hot path)
    user_id TEXT,
    success BOOLEAN DEFAULT TRUE,
    notes TEXT
);
```

Query examples:
```sql
-- Hot path p50/p95 latency
SELECT 
    ROUND(AVG(latency_ms), 1) as p50,
    ROUND(MAX(latency_ms), 1) as p95
FROM memory_metrics 
WHERE operation = 'hot_retrieve' 
AND ts > datetime('now', '-1 hour');

-- Memory store rate
SELECT DATE(ts), COUNT(*) as memories_stored
FROM memory_metrics
WHERE operation = 'cold_ingest' AND success = TRUE
GROUP BY DATE(ts);
```
