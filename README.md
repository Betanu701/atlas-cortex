# Atlas Cortex

A self-evolving AI assistant system built on top of [Open WebUI](https://github.com/open-webui/open-webui) and [Ollama](https://ollama.com). Atlas Cortex transforms a standard LLM chat into a **self-learning, personality-evolving home AI** that gets faster, smarter, and more human over time.

## What It Does

- **Instant answers** (~5ms) — date/time, math, identity questions with zero LLM overhead
- **Direct smart home control** (~100ms) — executes Home Assistant commands via API, no LLM round trip
- **Self-learning patterns** — commands that fall through to the LLM are analyzed nightly and converted into fast regex patterns
- **Sentiment-aware filler streaming** — starts responding immediately with contextual phrases while the LLM generates the real answer
- **Spatial awareness** — knows which room you're in via satellite mics, presence sensors, and speaker identity to scope commands automatically
- **Voice identification** — recognizes household members by voice and personalizes responses
- **Emotional evolution** — builds unique personality traits per user relationship over time
- **Age-appropriate responses** — adapts vocabulary, tone, and content filtering for toddlers, children, teens, and adults
- **Persistent memory** — HOT/COLD architecture with vector search, BM25, and RRF fusion for instant context recall
- **Conversational onboarding** — learns about users naturally through conversation, never overwrites, always builds upon
- **Animated avatar** — lip-synced face on satellite displays using phoneme-to-viseme mapping, emotion-driven expressions
- **Honest personality** — pushes back on bad ideas, challenges users in tutoring mode, never sycophantic
- **Anti-hallucination** — internal confidence scoring, grounding loops, mistake tracking and learning
- **Personal knowledge access** — indexes files, email, messages, calendar with strict user-scoped privacy

## Architecture

```
User Message (typed or voice)
         │
         ▼
┌─────────────────────────────────────┐
│         Atlas Cortex Pipe           │
│                                     │
│  Layer 0: Context    (~1ms)         │
│    User ID, sentiment, time-of-day  │
│                                     │
│  Layer 1: Instant    (~5ms)         │
│    Date, math, greetings, identity  │
│                                     │
│  Layer 2: Commands   (~100ms)       │
│    HA device control, learned       │
│    patterns, direct API calls       │
│                                     │
│  Layer 3: LLM        (~500-4000ms)  │
│    Filler stream → Ollama API       │
│    Auto-selects model by complexity │
│                                     │
│  Logger: every interaction saved    │
└─────────────────────────────────────┘
         │
         ▼ (nightly)
┌─────────────────────────────────────┐
│       Evolution Engine              │
│  • Discover new HA devices          │
│  • Learn patterns from fallthrough  │
│  • Evolve emotional profiles        │
│  • Optimize pattern database        │
└─────────────────────────────────────┘
```

## Hardware Target

- **Server:** Unraid (Overwatch) at 192.168.3.8
- **GPU:** AMD Radeon RX 7900 XT (20GB VRAM, RDNA3)
- **CPU:** AMD Ryzen 7 5700G (8c/16t, 128GB DDR4)
- **Models:** Qwen3 30B-A3B (thinking), Qwen2.5 14B (fast)
- **Stack:** Ollama (ROCm) + Open WebUI + SearXNG + faster-whisper + piper

## Project Structure

```
atlas-cortex/
├── README.md                  # This file
├── docs/
│   ├── architecture.md        # Detailed system architecture
│   ├── data-model.md          # Database schema and relationships
│   ├── memory-system.md       # HOT/COLD memory with vector search
│   ├── user-profiles.md       # Age-awareness, onboarding, profile evolution
│   ├── personality.md         # Honesty system, pushback, tutoring mode
│   ├── grounding.md           # Anti-hallucination, confidence scoring, mistake learning
│   ├── knowledge-access.md    # File/email/message indexing, user-scoped privacy
│   ├── avatar-system.md       # Lip-sync avatars, visemes, multi-skin
│   ├── phases.md              # Implementation phases and dependencies
│   └── infrastructure.md      # Current server/container topology
├── src/
│   ├── pipe/                  # Open WebUI Pipe function (core)
│   ├── memory/                # HOT/COLD memory engine
│   ├── evolution/             # Nightly cron job scripts
│   └── speaker-id/            # Speaker identification sidecar
├── config/
│   └── docker-compose.yml     # Container deployment (evolution + speaker-id)
├── seeds/
│   └── command_patterns.sql   # Initial HA command patterns
└── tests/
    ├── test_sentiment.py
    ├── test_patterns.py
    ├── test_memory.py
    └── test_instant.py
```

## Implementation Phases

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| C1 | Core Pipe | 🔲 Planned | Sentiment, instant answers, HA commands, filler streaming, logging |
| C2 | Self-Learning | 🔲 Planned | Nightly device discovery, fallthrough analysis, pattern generation |
| C3 | Voice Identity | 🔲 Planned | Speaker recognition, enrollment, spatial awareness |
| C4 | Emotional Evolution | 🔲 Planned | Rapport tracking, personality drift, proactive suggestions |
| C5 | Memory System | 🔲 Planned | HOT/COLD paths, vector search, BM25, RRF fusion, ChromaDB |
| C6 | User Profiles | 🔲 Planned | Age-awareness, onboarding, parental controls, profile evolution |
| C7 | Avatar System | 🔲 Future | Phoneme-to-viseme lip-sync, emotion expressions, multi-skin |
| C8 | Knowledge Access | 🔲 Future | File/email/message indexing, user-scoped privacy, source connectors |

See [docs/phases.md](docs/phases.md) for detailed task breakdown and dependency graph.

## Prerequisites

- [Ollama](https://ollama.com) with ROCm (AMD GPU) or CUDA (NVIDIA)
- [Open WebUI](https://github.com/open-webui/open-webui) v0.8.5+
- [Home Assistant](https://www.home-assistant.io/) with long-lived access token
- Python 3.11+

## License

MIT
