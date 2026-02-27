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
| C7 | Avatar System | 🔲 Planned | Phase C1 + C3 complete |
| C8 | Knowledge Access & Privacy | 🔲 Planned | Phase C5 + C6 complete |
| C9 | Backup & Restore | 🔲 Planned | None |
| C10 | Context Management & Hardware | 🔲 Planned | None |

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

## Phase C7: Avatar System (Future)

Visual face for Atlas displayed on satellite screens. See [avatar-system.md](avatar-system.md) for full design.

### C7.1 — Avatar Server Container
- FastAPI + WebSocket server (atlas-avatar, port 8891)
- Receives TTS audio + phoneme timing from Piper
- Receives emotion state from Cortex pipe
- Routes viseme + emotion frames to correct satellite display via WebSocket
- Serves the avatar web page (HTML/CSS/JS/SVG)

### C7.2 — Phoneme Extraction
- Integrate with Piper TTS phoneme output or espeak-ng
- Generate timed phoneme sequences from TTS text
- Handle streaming chunks (sentence-boundary splitting)

### C7.3 — Viseme Mapping & Sequencing
- Map ~40 IPA phonemes → 13 viseme mouth shapes (Preston Blair simplified)
- Generate timed viseme sequences synced to audio timestamps
- Smooth transitions between visemes (interpolation, not snapping)

### C7.4 — Browser-Based Avatar Renderer (Tier 2: SVG)
- SVG/Canvas2D face with eyes, mouth, eyebrows
- Mouth morphs between viseme shapes via CSS/JS animation
- Idle behaviors: blinking (3-6s random), breathing bob, eye drift
- Responsive — works on tablets, phones, wall displays

### C7.5 — Emotion Integration
- Drive eye shape, eyebrow position, mouth modifier from sentiment engine
- Emotional transitions blend over 300-500ms (ease-in-out)
- Time-of-day expressions (sleepy at night, bright in morning)
- Background color/mood tinting based on emotional state

### C7.6 — Audio-Viseme Synchronization
- Audio and viseme stream start at same timestamp
- 100ms buffer for network jitter absorption
- Satellite client uses shared clock for playback + animation sync
- Incremental streaming: animate while LLM is still generating

### C7.7 — ASCII Avatar (Tier 1)
- Text-based faces for ESP32 OLED and terminal displays
- Viseme + emotion combinations as ASCII art strings
- MQTT or WebSocket delivery to tiny displays
- Minimal resource usage

### C7.8 — Multi-Skin System
- Skin manifest format (JSON): colors, animation FPS, display requirements
- Skin directory structure: face, eyes, mouths (per viseme), brows (per emotion)
- Built-in skins: Orb (default), Bot, Buddy, Minimal, Classic (ASCII)
- Per-satellite or per-user skin selection

### C7.9 — ComfyUI Asset Generation (Optional)
- Use ComfyUI to generate consistent avatar art for custom skins
- img2img for viseme × emotion combination sheets
- Store generated assets as skin packs

---

## Phase C8: Knowledge Access & Data Privacy (Future)

Personal file/message/calendar indexing with strict user-scoped access control. See [knowledge-access.md](knowledge-access.md) for full design.

### C8.1 — Knowledge Index Infrastructure
- ChromaDB `cortex_knowledge` collection (separate from memory)
- SQLite `knowledge_docs` metadata table + FTS5 mirror
- Access gate: filter all queries by owner_id + access_level
- Identity confidence determines access tier (private/shared/household/public)

### C8.2 — Source Connectors
- Nextcloud (WebDAV): files, photos (EXIF), notes
- Email (IMAP): subject, body, attachments
- Calendar (CalDAV): events, shared calendars
- NAS (SMB/NFS): documents on file shares
- HA history: device states, automation logs
- Chat history: prior Atlas conversations

### C8.3 — Document Processing Pipeline
- Text extraction: PDF, DOCX, XLSX, CSV, Markdown, plain text
- Chunking for large documents
- Owner assignment from source path / account
- Access level assignment (private default, shared/household by path convention)
- PII tagging (tag, don't redact — it's the user's own data)
- Embed via Ollama, upsert to ChromaDB + FTS5

### C8.4 — Privacy Enforcement
- User-scoped queries: owner_id filter on all retrievals
- Unknown speaker: household + public data only
- Low-confidence speaker: shared + household + public only
- Cross-user data requests blocked with natural explanation
- Children's data visible to their parent (parental_controls)
- Children cannot access parent's private data
- Exclusion list: passwords, alarm codes, SSH keys, .env files, medical, financial

### C8.5 — Sync & Freshness
- Nightly full scan for all sources
- Real-time: HA states (WebSocket), chat history (interaction logger)
- Frequent: calendar (15min), email (30min)
- On-demand reindex triggered by user request
- Change detection via content hash (only re-embed modified docs)

### C8.6 — List Management
- List registry table with backend, permissions, aliases
- Backend adapters: HA to-do, Nextcloud CalDAV, file-based, Grocy, Todoist
- List resolution: explicit name → category inference → conversation context → memory → ask
- Permission enforcement: public lists allow anyone, private/shared respect access control
- Auto-discovery of lists from HA, Nextcloud, file paths during nightly job
- Remember routing preferences so user never repeats a clarification

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
| C9.1 | Build backup/restore CLI tool |
| C10.1 | Hardware auto-detection and limit computation |

## Blockers

- **C1.1 (Core Pipe)** requires HA long-lived access token to execute device commands
- **C3.2+** requires speaker-id sidecar deployed and accessible
- **C4.x** requires self-learning, voice identity, and memory all operational
- **C5.2+** requires embedding model (C5.1) operational
- **C6.x** requires both memory (C5) and speaker-id (C3) for full functionality

---

## External Projects (separate repos)

- [ ] **Document Classification System** — standalone service that classifies documents by type, sensitivity, and access level. Consumed by Atlas Cortex (C8) for automatic `access_level` assignment, PII detection, and content categorization. Should support: file type detection, content analysis, sensitivity scoring, category tagging (financial, medical, personal, work, household). Could use a fine-tuned small model or rule-based engine. Lives outside this project as a general-purpose utility.

---

## Phase C9: Backup & Restore

See [backup-restore.md](backup-restore.md) for full design.

### C9.1 — Backup/Restore CLI Tool
- `python -m cortex.backup create` — manual snapshot
- `python -m cortex.backup restore --latest daily` — one-command restore
- SQLite online backup (no locks, consistent snapshot)
- ChromaDB directory copy
- Config and avatar skins included
- Compressed tar.gz archives

### C9.2 — Automated Nightly Backups
- Integrated into nightly evolution job (runs first, before any changes)
- Retention: 7 daily, 4 weekly, 12 monthly
- Pre-operation safety snapshots (before migrations, bulk imports, upgrades)
- Disk space monitoring and backup health checks

### C9.3 — NAS Offsite Sync
- rsync to NAS share after each backup
- Ensures recovery even if Overwatch server fails completely
- Configurable remote path via cortex.env

### C9.4 — Voice-Accessible Backup Management
- "Atlas, back yourself up" → manual backup
- "Atlas, restore from yesterday" → restore with safety backup first
- "Atlas, when was your last backup?" → query backup_log
- Proactive warnings if backup health degrades

---

## Phase C10: Context Management & Hardware Abstraction

See [context-management.md](context-management.md) for full design.

### C10.1 — Hardware Auto-Detection
- GPU detection: AMD (ROCm), NVIDIA (CUDA), Intel (oneAPI), Apple (Metal), CPU-only
- Auto-compute VRAM budget, KV cache limits, max context window, model size cap
- Store in `hardware_profile` table, re-detect on demand or after OOM
- First-run installation wizard with recommended models

### C10.2 — Dynamic Context Sizing
- Per-request context window based on task complexity (512 for commands, 16K+ for reasoning)
- Token budget allocation: system → memory → active messages → checkpoints → generation reserve
- Thinking mode gets expanded context with pre-think compaction
- GPU memory monitoring to prevent OOM (reduce context or skip thinking when constrained)

### C10.3 — Context Compaction & Overflow Recovery
- Tiered summarization: checkpoint summaries (oldest) → recent summary → active messages (verbatim)
- Compaction triggers at 60% and 80% of context budget
- LLM-generated checkpoint summaries preserving decisions, entities, unresolved items
- Checkpoint expansion on demand if LLM needs detail from old segment
- **Transparent overflow recovery**: if output exceeds generation reserve, capture partial output, compact, re-send with continuation prompt — user never sees the seam
- **Chunked generation**: proactive splitting for long outputs (code, plans, detailed explanations)
- **Output deduplication**: sentence-level fuzzy matching to remove overlap across chunks, with coherence smoothing pass
- **Continuation fillers**: natural bridging phrases ("Bear with me...", "...and continuing with that...") streamed during recovery latency

### C10.4 — Hardware-Agnostic Model Selection
- Auto-recommend fast/standard/thinking/embedding models based on VRAM tier
- User overridable ("Atlas, use qwen3:30b for everything")
- Model config stored in `model_config` table
- Fallback chains: if preferred model doesn't fit, downgrade gracefully

### C10.5 — Context Observability
- `context_metrics` table tracking token budgets, utilization, compactions per request
- `context_checkpoints` table for conversation history compression
- Nightly evolution reviews metrics to tune default windows and thresholds

### C10.6 — User Interruption Handling
- Detect incoming messages during active generation (non-blocking poll)
- Classify interrupt type: stop, redirect, clarify, refine (pattern-based, no LLM)
- Stop: halt immediately, save partial output, natural acknowledgment
- Redirect: halt, checkpoint partial, begin new request with prior context
- Clarify: pause, answer inline, offer to resume
- Refine: halt, re-generate with refinement instruction
- Voice interruption: echo cancellation, listen-during-playback, wake word detection mid-output
