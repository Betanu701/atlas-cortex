# GPU Choreography: Treating VRAM Like an OS Treats RAM

> **TL;DR:** When you have 2 GPUs and 5 models that can't all fit at once, you need an
> orchestration layer that dynamically loads and unloads models based on real-time demand —
> just like an operating system manages RAM with page faults and priority preemption.

---

## The Problem

Running a full-featured personal AI requires multiple models simultaneously:

| Model | Purpose | VRAM Needed |
|---|---|---|
| Core LLM | Conversation, reasoning, routing | 3-5 GB |
| TTS (Orpheus) | Voice synthesis with emotions | 5-7 GB |
| Coding Expert | Self-evolution, code generation | 5-6 GB |
| Domain Expert | Deep knowledge (medical, science, etc.) | 5-7 GB |
| STT (Whisper) | Speech-to-text | 1-2 GB |

**Total if all loaded: ~19-27 GB**

Our hardware:
- **GPU 1 (RTX 4060):** 8 GB VRAM — "The Voice"
- **GPU 2 (RX 7900 XT):** 20 GB VRAM — "The Brain"
- **Combined:** 28 GB

28 GB seems like enough, but models can't be split across GPUs with different
architectures (CUDA vs. ROCm). We need to decide what lives where, and some models
need to time-share the same GPU.

---

## The Insight: GPU VRAM as Managed Memory

Operating systems solved this problem decades ago for RAM:

| OS Concept | GPU Choreography Equivalent |
|---|---|
| Resident set | Models currently loaded in VRAM |
| Page fault | Query arrives, needed model isn't loaded |
| Page-in | Load model into VRAM |
| Page-out / eviction | Unload model to free VRAM |
| Priority scheduling | User-facing models preempt background tasks |
| Working set | Models needed for current workload phase |

The key principles:
1. **User-facing latency is sacred** — TTS and core LLM get priority
2. **Background tasks yield** — Self-evolution, benchmarking defer to user queries
3. **Preemptive loading** — Start loading TTS before you know you need it
4. **Graceful degradation** — If a model can't fit, fall back to CPU or smaller variant

---

## Architecture: The Model Manager

```
                    ┌──────────────────┐
                    │   ModelManager    │
                    │                  │
                    │  ┌────────────┐  │
     User Query ───►│  │  Priority   │  │
                    │  │  Scheduler  │  │
                    │  └─────┬──────┘  │
                    │        │         │
                    │  ┌─────▼──────┐  │
                    │  │   VRAM     │  │
                    │  │  Allocator │  │
                    │  └─────┬──────┘  │
                    │        │         │
                    └────────┼─────────┘
                             │
                 ┌───────────┼───────────┐
                 │                       │
          ┌──────▼──────┐         ┌──────▼──────┐
          │  GPU 1      │         │  GPU 2      │
          │  RTX 4060   │         │  RX 7900 XT │
          │  8 GB       │         │  20 GB      │
          │             │         │             │
          │  Orpheus    │         │  Core LLM   │
          │  (5-7 GB)   │         │  (3-5 GB)   │
          │             │         │  + Expert   │
          │  or         │         │  (5-7 GB)   │
          │             │         │             │
          │  Coder      │         │  + Whisper  │
          │  (5-6 GB)   │         │  (1-2 GB)   │
          └─────────────┘         └─────────────┘
```

### The Python Interface

```python
class ModelManager:
    """Orchestrates model loading/unloading across GPUs."""
    
    async def ensure_loaded(self, model: str, priority: Priority) -> ModelHandle:
        """Guarantee a model is loaded and ready.
        
        If the model is already loaded, returns immediately.
        If VRAM is insufficient, evicts lower-priority models first.
        If a higher-priority model needs space, this model may be evicted.
        """
        ...
    
    async def preload(self, model: str, priority: Priority) -> None:
        """Begin loading a model in the background.
        
        Non-blocking. Used for anticipatory loading (e.g., preload TTS
        when a user query arrives, before the LLM response is ready).
        """
        ...
    
    async def release(self, model: str) -> None:
        """Mark a model as no longer actively needed.
        
        Doesn't immediately unload — the model stays resident as a cache.
        But it becomes eligible for eviction if space is needed.
        """
        ...
```

---

## Workload Scenarios

### Scenario 1: Normal Conversation

```
Time ──────────────────────────────────────────────►

GPU 1 (4060):  [  Orpheus TTS (always resident)  ]
GPU 2 (7900):  [  Core LLM  ][  Whisper  ][  Core LLM  ]
                              ↑ STT runs   ↑ LLM responds

Latency: ~0ms model swap (both pre-loaded)
```

Orpheus stays resident on GPU 1. Core LLM stays resident on GPU 2. Whisper is small
enough (1-2 GB) to coexist with the core LLM on the 20 GB card. No swaps needed
for 80% of interactions.

### Scenario 2: Deep Knowledge Query (Expert Needed)

```
Time ──────────────────────────────────────────────►

GPU 1 (4060):  [  Orpheus TTS                     ]
GPU 2 (7900):  [Core LLM][route!][Load Expert][Expert Answer][Unload][Core LLM]
                                  ↑ ~2-4s load time

User hears: filler audio ("Let me think about that...")
```

The core LLM recognizes it can't answer well, routes to an expert. During the 2-4
second expert load time, the filler audio system plays pre-cached audio to mask latency.
After the expert answers, it's released (but cached in VRAM if space allows).

### Scenario 3: Self-Evolution (Background, Interruptible)

```
Time ──────────────────────────────────────────────►

GPU 1 (4060):  [Unload Orpheus][Load Coder][  Coding  ][  Coding  ]
GPU 2 (7900):  [  Core LLM plans changes  ][  Monitor for user queries  ]

                              ⚡ User speaks!
                              
GPU 1 (4060):  [INTERRUPT: Unload Coder][Load Orpheus][  TTS  ]
GPU 2 (7900):  [  Core LLM handles user  ][  Resume after response  ]
```

Self-evolution runs during idle hours (2-5 AM). Orpheus unloads from GPU 1, coding
expert loads in its place. But if a user query arrives at ANY point:

1. **Immediate:** Core LLM on GPU 2 starts processing (already loaded)
2. **Parallel:** GPU 1 begins unloading coder + loading Orpheus (~3-5s)
3. **Bridge:** Filler audio plays from cache during the TTS swap
4. **Resume:** Once user interaction completes, self-evolution resumes

**The user never waits for a model swap** — the filler cache and the always-resident
core LLM ensure continuous responsiveness.

### Scenario 4: Minimal Hardware (Single 8GB GPU)

```
Time ──────────────────────────────────────────────►

GPU:  [Core LLM][Answer][Unload][Load TTS][Speak][Unload][Load Core]
       ↑ query   ↑ text   ↑ swap  ↑ voice   ↑ done  ↑ swap

Self-evolution (two-phase):
GPU:  [Core LLM: Plan changes][Unload][Load Coder][Execute plan][Unload][Load Core]
```

On a single 8 GB GPU, models take turns. The sub-1B core model (~3-5 GB quantized)
leaves room for nothing else. But because it's so small, swaps are fast (~1-2s).

For self-evolution, see the companion article: [Two-Phase Self-Evolution on 8GB](../03-two-phase-selfmod/article.md).

---

## Implementation Details

### Priority Levels

```python
class Priority(IntEnum):
    CRITICAL = 0    # User-facing TTS — preempts everything
    HIGH = 1        # Core LLM — always available for user queries
    MEDIUM = 2      # Domain experts — loaded on demand
    LOW = 3         # Background tasks — coding expert, benchmarking
    IDLE = 4        # Speculative caching — pre-load likely-needed models
```

### Eviction Policy

When a model needs VRAM and there isn't enough:

1. Check for models with `Priority.IDLE` — evict oldest first
2. Check for models with `Priority.LOW` — evict if requester is `MEDIUM` or higher
3. Check for models with `Priority.MEDIUM` — evict only for `CRITICAL` or `HIGH`
4. **Never evict** `CRITICAL` or `HIGH` priority models for lower priority requests
5. If nothing can be evicted, queue the request and wait

### Preemption Hook

The pipeline installs a preemption hook that fires as soon as user input is detected:

```python
async def on_user_input_detected():
    """Called when STT detects speech or text arrives."""
    # Preemptively start loading TTS — by the time LLM generates
    # a response, TTS will be ready
    await model_manager.preload("orpheus-tts", Priority.CRITICAL)
    
    # If a background task is using GPU 1, the preload will
    # trigger eviction of the LOW-priority model
```

### Filler Audio Bridge

The existing filler cache (`cortex/filler/cache.py`) provides pre-synthesized audio
clips that play during model swaps:

- "Let me think about that..."
- "Good question..."
- "One moment..."

These are generated at startup and stored as PCM audio. They play from CPU memory —
no GPU needed. This masks 2-5 seconds of model swap latency completely.

### VRAM Monitoring

```python
async def get_vram_status() -> dict:
    """Query actual VRAM usage across all GPUs."""
    return {
        "gpu_0": {
            "name": "RTX 4060",
            "total_mb": 8192,
            "used_mb": 5600,
            "models_loaded": ["orpheus-tts"],
            "available_mb": 2592
        },
        "gpu_1": {
            "name": "RX 7900 XT",
            "total_mb": 20480,
            "used_mb": 7200,
            "models_loaded": ["atlas-core", "whisper-medium"],
            "available_mb": 13280
        }
    }
```

---

## Why This Hasn't Been Done Before

Most AI deployments fall into two categories:

1. **Cloud:** Unlimited GPUs, no need for choreography — just allocate more hardware
2. **Edge:** Single small model, no swapping needed

The middle ground — **multiple specialized models on consumer hardware** — is where
GPU choreography becomes essential. This is increasingly relevant as:

- Personal AI assistants gain more capabilities (TTS, STT, vision, self-evolution)
- Consumer GPUs grow but not fast enough for all models simultaneously
- Users want local/private AI without cloud dependency

The orchestration layer we describe doesn't exist in any framework we've found.
Ollama can load/unload models, but it doesn't have:
- Priority-based preemption
- Cross-GPU awareness
- Anticipatory preloading
- Integration with filler audio for latency masking
- Workload phase awareness (conversation vs. self-evolution)

---

## Metrics to Track

| Metric | Target | Why |
|---|---|---|
| Model swap time | < 3s (warm), < 5s (cold) | User-perceived latency |
| Preemption latency | < 500ms to begin eviction | Responsiveness to user input |
| VRAM utilization | > 85% | Don't waste expensive memory |
| User-perceived gap | 0s (masked by filler) | The whole point |
| Background task completion | > 90% before dawn | Self-evolution must finish |

---

## References

- [Ollama Multi-Model Guide](https://www.elightwalk.com/blog/run-multiple-ollama-models) — Current state of multi-model serving
- [vLLM Model Loading](https://docs.vllm.ai/) — High-performance model serving
- [NVIDIA MPS](https://docs.nvidia.com/deploy/mps/) — Multi-Process Service for GPU sharing
- [ROCm Documentation](https://rocm.docs.amd.com/) — AMD GPU compute platform
- [Atlas Cortex Filler Cache](https://github.com/Betanu701/atlas-cortex) — Pre-synthesized audio for latency masking
