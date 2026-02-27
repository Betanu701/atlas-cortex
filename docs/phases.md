# Atlas Cortex — Implementation Phases

## Phase Overview

| Phase | Name | Status | Prerequisites |
|-------|------|--------|---------------|
| C1 | Core Pipe | 🔲 Planned | HA long-lived access token |
| C2 | Self-Learning Engine | 🔲 Planned | Phase C1 complete |
| C3 | Voice Identity + Spatial | 🔲 Planned | Phase C1 complete |
| C4 | Emotional Evolution | 🔲 Planned | Phase C2 + C3 + C5 complete |
| C5 | Memory System (HOT/COLD) | 🔲 Planned | Phase C1 complete |
| C6 | User Profiles & Age-Awareness | 🔲 Planned | Phase C3 + C5 complete |

## Phase C1: Core Pipe

The foundational pipe function that replaces the existing Atlas Turbo / Atlas / Atlas Deep Thought models with a single intelligent router.

### C1.1 — Core Cortex Pipe Function
Create the Open WebUI Pipe function (~300 lines Python):
- VADER sentiment analysis (installed in pipe's `__init__`)
- Layer 1: instant answers (date, time, math, identity, greetings)
- Layer 2: seed command patterns for HA (hardcoded initial set)
- Layer 3: filler streaming + Ollama API background call
- Auto-select model based on query complexity (Turbo vs Atlas vs Deep)

### C1.2 — Interaction Logging System
- Create cortex.db SQLite database (mounted volume)
- Create all tables from [data-model.md](data-model.md)
- Log every interaction with full metadata
- Flag LLM fallthrough events that used HA tools

### C1.3 — HA Device Bootstrap
- Fetch all entities from HA REST API (`/api/states`)
- Populate `ha_devices` table
- Fetch HA areas (`/api/config/area_registry/list`) and map entities to rooms
- Generate initial command patterns for common device types
- Map friendly names → entity IDs with alias support
- Identify and register presence sensors per area into `presence_sensors` table

### C1.4 — Filler Streaming Engine
- Default filler pools per sentiment category
- Time-of-day aware fillers (morning, afternoon, late night)
- Background thread for Ollama streaming
- Smooth transition: inject filler context into LLM system prompt

### C1.5 — Register Atlas Cortex Model
- Register Cortex as a model in Open WebUI
- Set as default model
- Retire Atlas Turbo / Atlas / Atlas Deep Thought (Cortex replaces all three)

---

## Phase C2: Self-Learning Engine

The system that makes Cortex smarter every day.

### C2.1 — Nightly Evolution Cron Job
- Lightweight Python container with cron
- Schedule: run at 3 AM daily
- HA device discovery diff (new devices, removed devices, renamed)
- LLM-powered pattern generation for new devices
- Write results to `evolution_log`

### C2.2 — Fallthrough Analyzer
- Query interactions where `matched_layer = 'llm'` AND `llm_tool_calls` contain HA actions
- Use LLM to generate regex patterns from the natural language that triggered fallthrough
- Insert learned patterns into `command_patterns` with source `'learned'`
- Confidence scoring and deduplication

### C2.3 — Pattern Lifecycle Management
- Track `hit_count` per pattern
- Prune zero-hit patterns after 30 days
- Boost frequently-hit patterns
- Merge similar patterns into generalized forms
- Weekly report: "X% of HA commands now handled without LLM"

---

## Phase C3: Voice Identity

Speaker recognition for personalized voice interactions.

### C3.1 — Speaker ID Sidecar Container
- Docker container with resemblyzer library (CPU-based, ~200MB RAM)
- REST API:
  - `POST /enroll` — audio + user_id → store embedding
  - `POST /identify` — audio → user_id + confidence
- Cosine similarity matching against stored embeddings

### C3.2 — Voice Enrollment Flow
- Voice command trigger: "Hey Atlas, remember my voice"
- Multi-sample enrollment (3-5 utterances for accuracy)
- Link voice profile to Open WebUI user account
- Average embeddings across samples for robustness

### C3.3 — Cortex Pipe Integration
- Voice requests include speaker embedding in metadata
- Pipe calls speaker-id sidecar for identification
- Inject identified user context into all processing layers
- Unknown speaker handling: prompt for name, offer enrollment

### C3.4 — HA Voice Pipeline Integration
- Modify Wyoming STT pipeline to pass audio to speaker-id sidecar
- Return identified user with transcribed text
- HA automation context: "Derek said turn off lights" vs "Guest said..."

### C3.5 — Spatial Awareness Engine
- Map voice satellites to HA areas (`satellite_rooms` table)
- Query HA presence sensors in real-time during Layer 0
- Combine satellite ID + presence + speaker identity for room resolution
- Multi-mic proximity: compare audio energy across satellites for same utterance
- Ambiguity resolution: satellite+presence > satellite-only > presence-only > ask user
- Room-scoped entity filtering: "the lights" → only entities in resolved room
- Log all spatial resolutions to `room_context_log` for tuning
- Contextual multi-room commands: "goodnight" triggers floor/house-scoped scenes based on location

---

## Phase C4: Emotional Evolution

The personality layer that makes Atlas feel human.

### C4.1 — Emotional Profile Engine
- Initialize profile on first interaction
- Track `rapport_score`: +0.01 per positive, -0.02 per frustrated
- Detect communication style from message patterns
- Store time-of-day activity patterns
- Decay rapport by 0.005/day of no interaction

### C4.2 — Nightly Personality Evolution
- LLM reviews day's conversations per user
- Generates updated `relationship_notes`
- Creates new personalized filler phrases matching user's style
- Adjusts `preferred_tone` based on communication patterns
- "Personality drift" — Atlas slowly develops unique traits per relationship

### C4.3 — Contextual Response Personalization
- Morning: "Good morning, Derek. Coffee's probably brewing?"
- Late night: "Still at it? Here's what I found..."
- After absence: "Hey, haven't seen you in a couple days!"
- User frustrated: tone shifts to calm, direct, solution-focused
- User excited: matches energy, uses exclamation marks

### C4.4 — Memory and Proactive Suggestions
- Remember user preferences ("Derek likes lights at 40% in the evening")
- Proactive suggestions ("It's 10 PM — want me to set evening mode?")
- Conversation callbacks ("How'd that Docker fix work out?")

---

## Phase C5: Memory System (HOT/COLD Architecture)

Adapted from [agentic-memory-quest](https://github.com/Betanu701/agentic-memory-quest). See [memory-system.md](memory-system.md) for full design.

### C5.1 — Embedding Model Setup
- Pull `nomic-embed-text` into Ollama (274MB, CPU-friendly)
- Verify embedding API: `POST /api/embeddings` returns 768-dim vectors
- Benchmark: target <10ms per embedding on CPU

### C5.2 — ChromaDB Integration
- Deploy ChromaDB in embedded mode (inside Cortex pipe or sidecar)
- Create `cortex_memory` collection with HNSW index
- Persistent storage on mounted volume
- Metadata schema: user_id, type, source, tags, supersedes, ttl, confidence

### C5.3 — HOT Path (Read)
- Compute query embedding via Ollama
- Sparse search: SQLite FTS5 (BM25 scoring)
- Dense search: ChromaDB vector similarity (cosine)
- RRF Fusion (k=60) to merge ranked lists
- Optional cross-encoder reranker (`ms-marco-MiniLM-L-6-v2`)
- Return top-K (default 8) MemoryHits, sub-50ms target

### C5.4 — COLD Path (Write)
- asyncio.Queue for non-blocking writes
- PII redactor (regex-based: emails, phones, SSN, CC numbers)
- Memory decider: heuristics for keep/drop/dedup (preference, fact, chit-chat)
- Embed via Ollama, upsert to ChromaDB + FTS5 mirror
- Append-only: corrections link to originals, never overwrite
- Content-hash dedup for idempotency

### C5.5 — Memory Integration with Pipe Layers
- Layer 0: HOT query to retrieve user memories on every request
- Layer 1: Memory-powered instant answers ("what's my daughter's name?")
- Layer 2: Memory-powered personalized defaults ("set lights" → remembered preference)
- Layer 3: Inject memory context into LLM system prompt
- COLD path fires after every interaction to capture new memories

---

## Phase C6: User Profiles & Age-Awareness

See [user-profiles.md](user-profiles.md) for full design.

### C6.1 — User Profile Engine
- SQLite `user_profiles` table for fast structured queries
- Profile fields: age, age_group, vocabulary_level, preferred_tone, communication_style
- Append-only profile evolution with confidence scoring
- Parent-child relationships (`parent_user_id` foreign key)

### C6.2 — Conversational Onboarding
- First encounter detection (new user_id or unknown voice)
- Natural "meeting someone new" dialogue flow
- Gradual profile building through conversation (not interrogation)
- "We've talked before" handling — search memory, re-link profiles

### C6.3 — Age-Appropriate Response Adaptation
- Response profiles: toddler, child, teen, adult, unknown/neutral
- Vocabulary filtering by age group
- Content safety filtering for children
- Tone adaptation: warm+simple (toddler) → casual+respectful (teen) → personalized (adult)
- System prompt modifier injected based on detected age group

### C6.4 — Parental Controls
- `parental_controls` table: content filter level, allowed devices, allowed hours
- Children can only control devices on their allowed list
- Time-based restrictions (e.g., no smart home control after 9 PM for kids)
- Sensitive commands require parent confirmation

### C6.5 — Voice-Based Age Estimation
- Extract pitch, cadence, speech rate from speaker-id audio
- Vocabulary complexity analysis from transcript
- Low-confidence heuristic (used as initial hint only, refined through interaction)
- Never tell a user their estimated age — only use internally for tone

---

## Dependency Graph

```
C1.1 (Core Pipe) ──────┬──▶ C1.4 (Filler Engine) ──▶ C1.5 (Register Model)
                        │
C1.3 (HA Bootstrap) ───┤
                        │
C1.2 (Logging) ────────┴──▶ C2.1 (Nightly Job) ──▶ C2.2 (Fallthrough)
                                    │                       │
                                    ▼                       ▼
                              C2.3 (Pattern Lifecycle)      │
                                                            │
C3.1 (Speaker Sidecar) ──▶ C3.2 (Enrollment) ──▶ C3.3 (Pipe Integration)
                                                       │
                                                       ▼
                                                  C3.4 (HA Voice)
                                                       │
                                                       ▼
                                                  C3.5 (Spatial Awareness)
                                                       │
C5.1 (Embedding Model) ──▶ C5.2 (ChromaDB) ──────────┤
                                │                      │
                                ▼                      │
                           C5.3 (HOT Path)             │
                                │                      │
                                ▼                      │
                           C5.4 (COLD Path)            │
                                │                      │
                                ▼                      ▼
                           C5.5 (Pipe Integration) ──▶ C6.1 (Profile Engine)
                                                            │
                                                            ▼
                                                  C6.2 (Onboarding)
                                                            │
                                                            ▼
                                                  C6.3 (Age Adaptation)
                                                       │         │
                                                       ▼         ▼
                                                  C6.4 (Parental) C6.5 (Voice Age)
                                                       │
                              C4.1 (Profile Engine) ◀──┘
                                    │
                                    ▼
                              C4.2 (Nightly Evolution) ──▶ C4.3 (Personalization)
                                                                │
                                                                ▼
                                                          C4.4 (Memory Proactive)
```

## What Can Start Now (No Dependencies)

| Task | Description |
|------|-------------|
| C1.2 | Create database schema and logging infrastructure |
| C1.3 | Fetch HA devices and build initial pattern set |
| C3.1 | Build speaker ID sidecar container |
| C5.1 | Pull embedding model into Ollama, verify API |

## Blockers

- **C1.1 (Core Pipe)** requires HA long-lived access token to execute device commands
- **C3.2+** requires speaker-id sidecar deployed and accessible
- **C4.x** requires self-learning, voice identity, and memory all operational
- **C5.2+** requires embedding model (C5.1) operational
- **C6.x** requires both memory (C5) and speaker-id (C3) for full functionality
