# Atlas Cortex — Avatar System

## Vision

Atlas gets a face. A simple, expressive, animated avatar displayed on screens near the user — think **Nick Jr. Face**, **Weebo from Flubber**, **Sonny's eye from I, Robot**, or even minimalist ASCII art. The avatar lip-syncs to Atlas's speech in real-time by mapping phonemes to mouth shapes (visemes), and expresses emotion through eye/brow animations driven by the sentiment engine.

The goal is **warmth and personality, not realism**. Simple geometric shapes with expressive animation feel more alive than an uncanny valley 3D face.

---

## Inspiration & Style Tiers

Atlas supports multiple avatar styles, selectable per-satellite or per-user preference:

### Tier 1: ASCII / Terminal
Zero dependencies. Runs on any screen, including tiny ESP32 OLED displays.

```
  Idle:          Talking:         Happy:          Thinking:
  
  ╭─────────╮    ╭─────────╮    ╭─────────╮    ╭─────────╮
  │  ◉   ◉  │    │  ◉   ◉  │    │  ◉   ◉  │    │  ◉   ◉  │
  │         │    │         │    │         │    │    ···   │
  │   ───   │    │   ╭─╮   │    │  ╰───╯  │    │   ───   │
  ╰─────────╯    ╰─────────╯    ╰─────────╯    ╰─────────╯
  
  Surprised:     Frustrated:     Sleeping:       Listening:
  
  ╭─────────╮    ╭─────────╮    ╭─────────╮    ╭─────────╮
  │  ◎   ◎  │    │  ◉   ◉  │    │  ─   ─  │    │  ◉   ◉  │
  │         │    │         │    │         │    │         │
  │   ╭─╮   │    │   ~~~   │    │   ───   │    │   ···   │
  ╰─────────╯    ╰─────────╯    ╰─────────╯    ╰─────────╯
```

### Tier 2: Simple Vector / SVG
Geometric shapes with smooth animation. Think Nick Jr. Face — a circle/rounded-rect with big expressive eyes and a simple mouth. Renders in any web browser.

```
Design elements:
  • Face: rounded rectangle or circle, solid color (soft blue/teal)
  • Eyes: large ovals, pupils that track... nothing (just shift with emotion)
  • Eyebrows: simple arcs that convey emotion
  • Mouth: bezier curve that morphs between viseme shapes
  • Optional: subtle idle animation (gentle bob, eye blinks every 3-5 sec)
```

### Tier 3: Animated Sprite / Pixel Art
Pre-rendered sprite sheets for each expression + viseme combo. Retro charm, efficient to display. Could be generated once by an image model (ComfyUI) and cached.

### Tier 4: 3D Orb / Weebo Style
A floating orb/sphere with a projected face. More complex but very recognizable. Could be a Three.js WebGL scene or pre-rendered animation loops.

---

## Phoneme-to-Viseme Pipeline

The core animation system: convert text-to-speech output into mouth shapes in real-time.

### What Are Visemes?

Visemes are the visual equivalent of phonemes — the mouth shapes that correspond to speech sounds. English has ~40 phonemes but only needs **~10-12 distinct visemes** because many phonemes look the same on the face.

### Viseme Set (Preston Blair standard, simplified)

| Viseme | Phonemes | Mouth Shape | Description |
|--------|----------|-------------|-------------|
| `REST` | (silence) | `───` | Closed, neutral |
| `AA` | a, æ, ʌ | `╭───╮` | Wide open |
| `EE` | i, ɪ, e | `╭─╮` | Wide smile, teeth visible |
| `OO` | u, ʊ, o | `( ○ )` | Small round |
| `OH` | ɔ, ɑ | `╭─────╮` | Tall open oval |
| `AH` | ə, ɜ | `╭───╮` | Medium open |
| `EH` | ɛ, eɪ | `╭──╮` | Slightly open, wide |
| `FF` | f, v | `─┘` | Bottom lip tucked |
| `TH` | θ, ð | `─╥─` | Tongue between teeth |
| `MM` | m, b, p | `───` | Lips pressed together |
| `NN` | n, t, d, l | `╭╮` | Slightly open, tongue up |
| `SS` | s, z, ʃ, ʒ | `═══` | Teeth together, slightly open |
| `WW` | w, r | `( )` | Puckered/rounded |

### Pipeline

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Piper TTS   │────▶│  Phoneme     │────▶│  Viseme      │
│  (audio +    │     │  Extractor   │     │  Mapper      │
│   phonemes)  │     │              │     │              │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
                                                  ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Satellite   │◀────│  WebSocket   │◀────│  Viseme      │
│  Display     │     │  Stream      │     │  Sequencer   │
│  (browser)   │     │              │     │  (timed)     │
└──────────────┘     └──────────────┘     └──────────────┘
```

#### Step 1: Phoneme Extraction

Piper TTS already generates phonemes internally (it's an IPA-based system). Options:

- **Piper phoneme output**: Piper can output phoneme timing via `--output-raw` + phoneme callback
- **espeak-ng**: Standalone phonemizer, can generate IPA + timing from text
- **gruut**: Python library for text-to-phoneme conversion with timing estimates

```python
# Using espeak-ng (available in most Linux containers)
# Input: "Hello, how are you?"
# Output: [
#   {"phoneme": "h",  "start": 0.00, "end": 0.05},
#   {"phoneme": "ɛ",  "start": 0.05, "end": 0.12},
#   {"phoneme": "l",  "start": 0.12, "end": 0.18},
#   {"phoneme": "oʊ", "start": 0.18, "end": 0.28},
#   ...
# ]
```

#### Step 2: Viseme Mapping

```python
PHONEME_TO_VISEME = {
    # Vowels
    'a': 'AA', 'æ': 'AA', 'ʌ': 'AA',
    'i': 'EE', 'ɪ': 'EE', 'e': 'EE',
    'u': 'OO', 'ʊ': 'OO', 'o': 'OO',
    'ɔ': 'OH', 'ɑ': 'OH',
    'ə': 'AH', 'ɜ': 'AH',
    'ɛ': 'EH',
    # Consonants
    'f': 'FF', 'v': 'FF',
    'θ': 'TH', 'ð': 'TH',
    'm': 'MM', 'b': 'MM', 'p': 'MM',
    'n': 'NN', 't': 'NN', 'd': 'NN', 'l': 'NN',
    's': 'SS', 'z': 'SS', 'ʃ': 'SS', 'ʒ': 'SS',
    'w': 'WW', 'r': 'WW',
    # Silence
    '': 'REST', ' ': 'REST',
}
```

#### Step 3: Viseme Sequencing

Generate a timed sequence of viseme frames synchronized with the audio:

```python
# Output: timed viseme sequence
[
    {"viseme": "MM",   "start": 0.00, "duration": 0.05},
    {"viseme": "EH",   "start": 0.05, "duration": 0.07},
    {"viseme": "NN",   "start": 0.12, "duration": 0.06},
    {"viseme": "OO",   "start": 0.18, "duration": 0.10},
    {"viseme": "REST", "start": 0.28, "duration": 0.05},
    ...
]
```

#### Step 4: WebSocket Stream to Satellite Display

```json
// Streamed over WebSocket to the satellite's browser-based display
{
    "type": "viseme",
    "data": {
        "viseme": "EE",
        "duration_ms": 80,
        "emotion": "happy",       // from sentiment engine
        "intensity": 0.7          // how strongly to express
    }
}
```

---

## Emotion-Driven Expression

The avatar doesn't just lip-sync — it **expresses emotion** from the sentiment engine:

| Emotion State | Eyes | Eyebrows | Mouth Modifier | Body |
|--------------|------|----------|---------------|------|
| Neutral | Normal | Flat | Normal shapes | Still |
| Happy | Slightly squinted | Raised | Wider, upturned corners | Gentle bob |
| Excited | Wide | High raised | Big smile | Bouncy |
| Thinking | Looking up/aside | One raised | Slightly pursed | Slow tilt |
| Listening | Normal, attentive | Slightly raised | Closed/neutral | Lean forward |
| Sad | Droopy | Angled down | Downturned | Slow droop |
| Frustrated | Narrowed | Furrowed | Tight/flat | Slight shake |
| Surprised | Very wide | Very raised | Open 'O' | Jump back |
| Sleeping | Closed (─ ─) | Relaxed | Neutral | Slow breathing |
| Error | X X or ◎ ◎ | Concerned | Wavy | Shake |

### Emotional Transitions

Emotions don't snap — they **blend** over 300-500ms:

```
happy ─── 400ms ease-in-out ───▶ thinking
  eyes: squinted → looking up
  brows: raised → one up
  mouth: smile → pursed
```

### Idle Behaviors (personality touches)

When Atlas isn't speaking or listening:
- **Blink** every 3-6 seconds (random interval, like a real person)
- **Gentle breathing** bob (subtle scale oscillation)
- **Eye drift** — slowly look around, then snap back when user speaks
- **Occasional micro-expressions** — small smile, slight brow raise
- **Time-of-day**: sleepy eyes late at night, bright eyes in morning

---

## Display Architecture

### Satellite Display Options

| Platform | Display | Rendering | Connection |
|----------|---------|-----------|------------|
| **ESP32-S3 + OLED** | 128x64 mono | ASCII visemes | MQTT/WebSocket |
| **ESP32-S3 + TFT** | 240x240 color | Sprite sheets | WebSocket |
| **RPi + screen** | Any resolution | Browser (SVG/Canvas) | Local HTTP |
| **Wall tablet** | 800x480+ | Browser (full SVG) | WiFi, browser |
| **Smart display** | Varies | Browser/app | WiFi |

### Rendering Stack (Browser-Based, Tier 2)

```
┌──────────────────────────────────────────────┐
│  Satellite Display (browser, fullscreen)      │
│                                               │
│  ┌─────────────────────────────────────────┐ │
│  │          Avatar Canvas (SVG/Canvas2D)    │ │
│  │                                          │ │
│  │  Background: gradient (mood-colored)     │ │
│  │  Face: rounded rect, soft shadow         │ │
│  │  Eyes: animated SVG paths                │ │
│  │  Mouth: morphing bezier (viseme targets) │ │
│  │  Particles: subtle ambient (optional)    │ │
│  │                                          │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  WebSocket ← atlas-avatar-server:8891         │
│  Audio     ← Piper TTS stream                │
│  Sync      ← viseme timestamps align to audio│
└──────────────────────────────────────────────┘
```

### Avatar Server (lightweight sidecar)

```
Container: atlas-avatar
Port: 8891

Responsibilities:
  1. Receive TTS audio + phoneme timing from Piper
  2. Map phonemes → visemes with timing
  3. Receive emotion state from Cortex pipe
  4. Receive spatial context (which satellite to target)
  5. Stream viseme + emotion frames via WebSocket to the correct satellite display
  6. Serve the avatar web page (HTML/CSS/JS/SVG)

Input:
  POST /speak { audio_url, phonemes[], emotion, target_satellite }
  WS   /stream → real-time viseme frames to connected displays

Tech: Python (FastAPI) + WebSocket, ~50MB container
```

---

## Multi-Avatar Support

Different avatars for different contexts or user preferences:

| Avatar | Style | Best For |
|--------|-------|----------|
| **Orb** | Floating circle with face | Default, works everywhere |
| **Bot** | Boxy robot face, LED-style eyes | Tech/playful feel |
| **Buddy** | Rounded friendly character | Kids, warm interactions |
| **Minimal** | Just eyes and mouth, no face shape | Tiny displays, OLED |
| **Classic** | ASCII art | Terminal, ESP32 OLED |
| **Custom** | User-designed SVG | Advanced users |

Each avatar is defined as a **skin** — a set of SVG templates for each viseme × emotion combination:

```
skins/
├── orb/
│   ├── manifest.json          # metadata, default colors
│   ├── face.svg               # base face shape
│   ├── eyes/
│   │   ├── neutral.svg
│   │   ├── happy.svg
│   │   ├── thinking.svg
│   │   └── ...
│   ├── mouths/
│   │   ├── REST.svg
│   │   ├── AA.svg
│   │   ├── EE.svg
│   │   ├── OO.svg
│   │   └── ... (13 visemes)
│   └── brows/
│       ├── neutral.svg
│       ├── raised.svg
│       ├── furrowed.svg
│       └── ...
├── bot/
│   └── ...
├── buddy/
│   └── ...
└── minimal/
    └── ...
```

### Skin Manifest

```json
{
    "name": "Orb",
    "id": "orb",
    "author": "Atlas Cortex",
    "version": "1.0",
    "base_color": "#4A9EBF",
    "accent_color": "#2D6B87",
    "supports_emotions": true,
    "supports_visemes": true,
    "min_display_size": "128x128",
    "animation_fps": 30,
    "blink_interval": [3, 6],
    "transition_ms": 300
}
```

---

## Asset Generation

For Tier 2+ avatars, assets can be generated using **ComfyUI** (already planned for the stack):

1. Design a base character in a consistent style
2. Generate all viseme × emotion combinations as images/SVGs
3. Use img2img for consistency across the set
4. Store as a skin pack

For Tier 1 (ASCII), the "assets" are just text strings — defined directly in code.

---

## Integration with Cortex Pipeline

```
User speaks → STT → text
                      │
                      ▼
              Atlas Cortex Pipe
              (processes, generates response)
                      │
          ┌───────────┼───────────────┐
          ▼           ▼               ▼
     Piper TTS    Avatar Server    Satellite Speaker
     (audio)      (visemes+emotion) (audio playback)
          │           │               │
          └───────────┼───────────────┘
                      ▼
              Satellite Display
              (synchronized: audio plays while avatar animates)
```

### Timing Synchronization

Critical: the mouth animation must be **synchronized with the audio**. Strategy:

1. Piper generates audio + phoneme timing in one pass
2. Avatar server pre-computes the full viseme sequence
3. Both audio and viseme stream start at the **same timestamp**
4. The satellite client plays audio and advances viseme frames using the same clock
5. Small buffer (100ms) to absorb network jitter

### Streaming During Response Generation

For long LLM responses, TTS and avatar animate incrementally:

```
LLM token stream:  "The | sky | is | blue | because..."
                      │
                      ▼ (sentence boundary or punctuation)
              Piper TTS (chunk: "The sky is blue")
                      │
                      ├──▶ Audio chunk → satellite speaker
                      └──▶ Phoneme timing → avatar server → viseme WS → display
              
              Next chunk streams while first chunk plays...
```

---

## Phase C7 Summary

| Task | Description |
|------|-------------|
| C7.1 | Avatar server container (FastAPI + WebSocket) |
| C7.2 | Phoneme extraction integration (Piper/espeak-ng) |
| C7.3 | Viseme mapping + sequencing engine |
| C7.4 | Browser-based avatar renderer (SVG/Canvas, Tier 2) |
| C7.5 | Emotion integration with sentiment engine |
| C7.6 | Audio-viseme synchronization |
| C7.7 | ASCII avatar for ESP32/OLED (Tier 1) |
| C7.8 | Multi-skin system + skin manifest format |
| C7.9 | ComfyUI asset generation pipeline (optional) |

### Dependencies

- Requires: Piper TTS (✅ running), sentiment engine (C1.1), spatial awareness (C3.5)
- Benefits from: emotional profiles (C4.x) for richer expressions
- Optional: ComfyUI for generated assets (maintenance task)
