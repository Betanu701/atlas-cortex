# Breaking the I/O Wall: Zero-I/O Pipeline Architecture

## The Dirty Secret Nobody Talks About

Every AI assistant framework — from LangChain to Haystack to custom pipelines — has
the same hidden bottleneck. It's not the LLM. It's not the embedding model. It's not
the vector database.

**It's HTTP.**

Your local LLM is generating tokens at 600+ tokens/sec, but you're talking to it
through an HTTP API. Your embeddings take 2ms to compute, but the round-trip through
a REST endpoint takes 20ms. Your safety checks are pure regex, but they're wrapped
in middleware that serializes and deserializes JSON.

We traced every single I/O operation in our pipeline and found **~135ms of pure
overhead** per query — for operations that should take ~3ms combined.

## The Audit: Where Does Time Actually Go?

We instrumented our 4-layer pipeline (context assembly, instant answers, plugin
dispatch, LLM generation) and measured every I/O boundary:

| Operation | What It Does | Actual Compute | I/O Overhead | Method |
|---|---|---|---|---|
| Safety check | Regex + semantic match | ~1ms | ~10ms | SQLite read (learned patterns) |
| Context assembly | Speaker ID, room, time | ~1ms | ~2ms | SQLite read |
| Memory retrieval | BM25 search + vector | ~5ms | ~40ms | SQLite FTS5 + ChromaDB HTTP |
| Filler selection | Pick a phrase | ~0.1ms | ~3ms | SQLite read |
| LLM inference | Generate response | ~500-4000ms | ~100ms | HTTP to Ollama |
| Interaction log | Write to DB | ~1ms | ~5ms | SQLite write |
| TTS synthesis | Generate speech | ~200-1500ms | ~30ms | HTTP to Kokoro/Orpheus |
| **Total overhead** | | | **~190ms** | |

Almost 200ms of pure overhead. On a sub-1B model that generates its first token in
50ms, **the overhead is 4x the actual compute**.

## The Insight: Personal AI Doesn't Need Distribution

The reason everything goes through HTTP is because AI frameworks assume you might
want to distribute components across machines. Ollama runs as a server because it
*might* serve multiple clients. ChromaDB runs as a server because it *might* be
shared. Even SQLite connections go through a connection pool because of the threading
model.

But a personal AI assistant is fundamentally different:
- **One user** (or one household)
- **One machine** (or one machine + satellites, but the brain is always local)
- **One pipeline** processing one query at a time

We don't need client-server. We need **in-process**.

## The Architecture: Everything In-Process

### In-Process LLM: llama-cpp-python

Instead of:
```
Python → HTTP POST → Ollama (Go) → llama.cpp → response → HTTP → Python
```

We do:
```
Python → llama-cpp-python (C library, GIL released) → response
```

The critical detail: **llama.cpp releases the Python GIL during inference**. This
means other Python coroutines (asyncio tasks) run concurrently while tokens are
being generated. You get the best of both worlds — in-process speed with async
concurrency.

```python
from llama_cpp import Llama

class InProcessProvider(LLMProvider):
    def __init__(self, model_path: str, n_gpu_layers: int = -1):
        self.llm = Llama(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=n_gpu_layers,  # Full GPU offload
            verbose=False,
        )
    
    async def generate(self, messages, **kwargs):
        # Runs in thread pool — GIL released during C execution
        response = await asyncio.to_thread(
            self.llm.create_chat_completion,
            messages=messages,
            stream=True,
        )
        for chunk in response:
            yield chunk["choices"][0]["delta"].get("content", "")
```

**Savings:** ~100ms per query (no HTTP serialization, no Go↔C bridging)

### In-Process Embeddings

Instead of calling Ollama's `/api/embeddings` or running a ChromaDB server:

```python
import numpy as np
from sentence_transformers import SentenceTransformer

class InProcessEmbedder:
    def __init__(self):
        self.model = SentenceTransformer("all-MiniLM-L6-v2")  # 80MB, CPU
        self.cache = {}  # LRU cache for repeated queries
    
    def embed(self, text: str) -> np.ndarray:
        if text in self.cache:
            return self.cache[text]
        vec = self.model.encode(text)
        self.cache[text] = vec
        return vec
```

**Savings:** ~35ms per query (no HTTP to embedding service)

### In-Memory Vector Index

Replace ChromaDB with numpy cosine similarity or FAISS:

```python
class InMemoryVectorIndex:
    def __init__(self):
        self.vectors = np.zeros((0, 384))  # MiniLM dimension
        self.metadata = []
    
    def search(self, query_vec: np.ndarray, k: int = 5):
        if len(self.vectors) == 0:
            return []
        # Pure numpy — no I/O, no serialization
        similarities = self.vectors @ query_vec
        top_k = np.argpartition(similarities, -k)[-k:]
        return [(self.metadata[i], similarities[i]) for i in top_k]
```

**Savings:** ~40ms per query (no ChromaDB HTTP)

### SQLite: Already Fast, Just Move Writes Off the Hot Path

SQLite reads are fast enough to stay synchronous. The win is moving writes
(interaction logging, cache updates) to fire-and-forget background tasks:

```python
# Hot path: only reads (cached connection, WAL mode)
# Cold path: writes happen after response is sent
asyncio.create_task(log_interaction_async(context, response))
```

**Savings:** ~5ms per query (deferred writes)

## The Result: 135ms → ~3ms

| Operation | Before | After | How |
|---|---|---|---|
| Safety check | ~11ms | ~1ms | In-memory patterns (already mostly there) |
| Context assembly | ~3ms | ~1ms | Direct SQLite read (keep as-is) |
| Memory retrieval | ~45ms | ~5ms | In-process embedding + numpy search |
| Filler selection | ~3ms | ~0.5ms | In-memory cache |
| LLM inference | ~600ms | ~500ms | In-process llama-cpp-python |
| Interaction log | ~6ms | ~0ms | Deferred to background |
| TTS synthesis | ~230ms | ~200ms | In-process embedding + direct CUDA |
| **Total overhead** | **~190ms** | **~3ms** | |

The pipeline becomes **compute-bound**, not I/O-bound. This is the correct state
for a personal AI. The model's inference speed IS the bottleneck, exactly as it
should be.

## The Trade-Off: What You Give Up

**Distribution.** With everything in-process, you can't run the LLM on one machine
and the pipeline on another. For a personal AI, this is the right trade-off. If you
later need distribution (multiple satellites sharing a brain), you add an in-process
RPC layer — still faster than HTTP.

**Ollama's Model Management.** Ollama handles model downloading, GGUF conversion,
and GPU layer splitting beautifully. With in-process inference, you manage this
yourself (or use Ollama's models directory but load them directly via llama-cpp-python).

**Multi-Model.** Ollama can hot-swap models. With in-process, model loading is
explicit and takes 2-5 seconds. Since our architecture uses LoRA adapters instead
of model swapping, this is fine — adapters load in <1ms.

## When Does This Matter?

For a standard 7B model generating at 50 tok/s, the LLM itself takes ~2 seconds
for a typical response. The 135ms overhead is ~7% — noticeable but not critical.

For a pruned sub-1B model at 200+ tok/s, the LLM takes ~200ms. The 135ms overhead
is **40% of total latency**. This is where zero-I/O becomes transformative.

The smaller your model, the more the overhead matters. As we push toward sub-1B
cores with LoRA adapters, the pipeline overhead becomes the dominant cost. Zero-I/O
is not optional for sub-1B inference — it's mandatory.

## References

- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — Python bindings for llama.cpp
- [FAISS](https://github.com/facebookresearch/faiss) — Billion-scale similarity search
- [sentence-transformers](https://www.sbert.net/) — Efficient text embeddings
- [SQLite WAL Mode](https://www.sqlite.org/wal.html) — Write-Ahead Logging for concurrent reads
