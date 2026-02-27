# Atlas Cortex — System Architecture

## Overview

Atlas Cortex is an Open WebUI **Pipe function** that intercepts all user messages and processes them through a multi-layer pipeline. Each layer is progressively more expensive — simple queries are answered instantly without touching the LLM, while complex queries get routed to the appropriate model with perceived-zero-latency filler streaming.

## Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     Atlas Cortex Pipe                            │
│                                                                  │
│  Input Sources:                                                  │
│    • Web UI (user_id known from session)                        │
│    • Voice via HA (speaker identified by embedding)             │
│                                                                  │
│  Processing Layers (executed sequentially, first match wins):   │
│                                                                  │
│  Layer 0: Context Assembly                          ~1ms        │
│    • Identify user (session or voice embedding)                 │
│    • Load emotional profile (rapport, tone, filler pool)        │
│    • Run VADER sentiment analysis on input                      │
│    • Check time-of-day for tone adjustment                      │
│                                                                  │
│  Layer 1: Instant Answers                           ~5ms        │
│    • Date/time/day-of-week                                      │
│    • Basic math (eval with safety sandbox)                      │
│    • Identity questions ("who are you", "what can you do")      │
│    • Greetings (time-of-day + user-name aware)                  │
│    • Recent memory recall (from interaction log)                │
│                                                                  │
│  Layer 2: Learned Device Commands                   ~100-200ms  │
│    • Pattern-match against command_patterns DB                  │
│    • Execute HA REST API directly (no LLM round trip)           │
│    • Patterns auto-generated from HA device discovery           │
│    • Patterns learned from LLM fallthrough analysis             │
│    • Returns natural response: "Done — bedroom lights off"      │
│                                                                  │
│  Layer 3: Filler + LLM Streaming                    ~500-4000ms │
│    • Select personalized filler based on sentiment + user       │
│    • Start streaming filler tokens immediately (0ms perceived)  │
│    • Fire Ollama API request in background thread               │
│    • When first real token arrives, seamlessly transition       │
│    • Inject filler context into system prompt so LLM continues  │
│      naturally from the filler text                             │
│                                                                  │
│  Always Running: Interaction Logger                             │
│    • Log every interaction: user, message, layer hit,           │
│      sentiment, entities, response time, tool calls             │
│    • If Layer 3 used HA tools → flag for pattern learning       │
│    • Feeds the nightly evolution job                            │
└─────────────────────────────────────────────────────────────────┘
```

## Nightly Evolution Job

Runs as a cron container at 3 AM daily. Uses the existing Qwen3 30B model for intelligent tasks.

```
┌─────────────────────────────────────────────────────────────────┐
│                   Nightly Evolution Job (cron)                   │
│                                                                  │
│  1. Device Discovery                                            │
│     • GET /api/states from HA → compare with ha_devices table   │
│     • New devices → LLM generates friendly names + aliases      │
│     • LLM generates command patterns (regex) for each device    │
│     • Insert into command_patterns DB (source: 'nightly')       │
│                                                                  │
│  2. Fallthrough Analysis                                        │
│     • Query interactions where matched_layer = 'llm'            │
│       AND llm_tool_calls includes HA actions                    │
│     • For each: LLM generates a regex pattern that would have   │
│       caught this at Layer 2                                    │
│     • Insert into command_patterns DB (source: 'learned')       │
│     • Over time, fewer queries fall through to LLM              │
│                                                                  │
│  3. Emotional Profile Evolution                                 │
│     • Per user: analyze day's interactions                      │
│     • Update rapport_score (interaction count, sentiment trend) │
│     • LLM generates updated relationship_notes                  │
│     • LLM generates new personalized filler phrases             │
│     • Adjust preferred_tone based on communication patterns     │
│     • Time-of-day patterns: morning greetings vs late-night     │
│                                                                  │
│  4. Pattern Optimization                                        │
│     • Prune patterns with 0 hits after 30 days                  │
│     • Boost confidence on frequently-hit patterns               │
│     • Merge similar patterns into more general ones             │
│     • Report: "Learned 12 new patterns, 94% of HA commands     │
│       now handled at Layer 2 (up from 87%)"                     │
└─────────────────────────────────────────────────────────────────┘
```

## Speaker Identification Sidecar

Lightweight CPU-based container using [resemblyzer](https://github.com/resemble-ai/Resemblyzer) for speaker embeddings.

```
┌─────────────────────────────────────────────────────────────────┐
│                  Speaker Identification Sidecar                  │
│                                                                  │
│  Container: atlas-speaker-id (CPU-based, ~200MB RAM)            │
│  Library: resemblyzer (d-vector embeddings, 256-dim)            │
│                                                                  │
│  Enrollment Flow:                                               │
│    User: "Hey Atlas, remember my voice"                         │
│    Atlas: "Sure! Say a few sentences so I can learn your voice" │
│    → Record 10-15 seconds → Generate embedding → Store          │
│    Atlas: "Got it, Derek. I'll know it's you next time."        │
│                                                                  │
│  Identification Flow:                                           │
│    Audio arrives → Extract embedding → Cosine similarity match  │
│    Threshold > 0.85 → Identified (inject user context)          │
│    Threshold < 0.85 → Unknown → "I don't recognize that voice.  │
│                        What's your name?"                       │
│                                                                  │
│  API: POST /identify { audio_base64 } → { user_id, confidence }│
│  API: POST /enroll   { audio_base64, user_id } → { success }   │
└─────────────────────────────────────────────────────────────────┘
```

## Filler Streaming — How It Works

The key insight: **start talking before you have the answer**, then seamlessly blend in the real response.

```
User: "Why is the sky blue?"

Timeline:
  0ms    → Sentiment: curious/question
  1ms    → No instant answer match, no HA command match
  2ms    → Select filler: "Good question — "
  3ms    → Start streaming filler tokens to user
  50ms   → Background thread: POST /api/chat to Ollama
  300ms  → Filler complete, user sees: "Good question — "
  800ms  → First real token arrives from Ollama
  801ms  → Continue streaming: "the sky appears blue because..."
  
User perceives: continuous response from 3ms
Actual LLM latency: 800ms (hidden behind filler)
```

### Filler Pools (default, personalized over time)

| Sentiment | Fillers |
|-----------|---------|
| Greeting | "Hey!", "Good morning!", "What's up?" |
| Question | "Good question — ", "Let me think... ", "Hmm, " |
| Frustrated | "I hear you. Let me help — ", "Yeah, that's annoying. " |
| Command | *(no filler — execute directly)* |
| Excited | "That's awesome! ", "Hell yeah! " |
| Late night | "Still at it? ", "Alright, " |

### LLM System Prompt Injection

To prevent the LLM from repeating the filler sentiment:

```
[injected before real system prompt]
You already started your response with: "Good question — "
Continue naturally from that point. Do NOT repeat the greeting or acknowledgment.
```

## Model Selection (Layer 3)

The pipe auto-selects the LLM based on query analysis:

| Signal | Model | Reasoning |
|--------|-------|-----------|
| Short question, factual | Qwen2.5 14B (Turbo) | Fast, no thinking overhead |
| Code, explanation, multi-step | Qwen3 30B-A3B | Thinking mode beneficial |
| "explain in detail", "analyze", "compare" | Qwen3 30B-A3B (Deep) | Full thinking budget |

Selection is rule-based (no LLM needed for routing):
- Message length, keyword detection, conversation depth, explicit user cues

## Technical Stack

| Component | Technology | Resource |
|-----------|-----------|----------|
| Core Pipe | Open WebUI Pipe function (Python) | Runs inside Open WebUI container |
| Sentiment | VADER (vaderSentiment) | CPU, <1ms |
| Speaker ID | resemblyzer | CPU, ~50ms, ~200MB RAM |
| Fast LLM | Qwen2.5 14B (abliterated) | RX 7900 XT, 55 tok/s |
| Thinking LLM | Qwen3 30B-A3B (MoE) | RX 7900 XT, 75 tok/s |
| Smart Home | Home Assistant REST API | Proxmox VM |
| Search | SearXNG | Self-hosted |
| STT | faster-whisper | Port 10300 |
| TTS | piper | Port 10200 |
| Nightly Job | Python + cron container | CPU only |
