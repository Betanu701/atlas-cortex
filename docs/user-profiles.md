# Atlas Cortex — User Profiles & Age-Appropriate Responses

## Overview

Atlas Cortex maintains rich, evolving profiles for every user it interacts with. Profiles are built through **conversational onboarding** (like meeting someone new), **passive observation** (sentiment patterns, vocabulary analysis), and **explicit input** (user tells Atlas about themselves). Profiles are **never overwritten** — only appended to, with corrections linking back to originals.

---

## User Profile Schema

```python
# Stored in ChromaDB as memory documents + structured in SQLite for fast queries

class UserProfile:
    user_id: str                    # Open WebUI user ID or speaker profile ID
    display_name: str               # "Derek", "Emma"
    
    # Demographics (learned, not assumed)
    age: int | None                 # actual age if known
    age_group: str                  # "toddler" | "child" | "teen" | "adult" | "unknown"
    gender: str | None              # only if explicitly stated
    
    # Communication profile
    preferred_tone: str             # "casual", "formal", "playful", "simple"
    vocabulary_level: str           # "basic", "intermediate", "advanced", "technical"
    communication_style: str        # "concise", "detailed", "questions-a-lot"
    humor_style: str | None         # "dry", "puns", "slapstick", "none"
    
    # Relationship with Atlas
    rapport_score: float            # 0.0 - 1.0
    interaction_count: int
    first_interaction: datetime
    last_interaction: datetime
    
    # Preferences (from memory system)
    preferences: list[str]          # retrieved via HOT path
    
    # Behavioral
    peak_hours: dict                # when they're typically active
    common_topics: list[str]        # what they usually ask about
    frustration_triggers: list[str] # what makes them impatient
```

---

## Age Groups & Response Adaptation

### Detection Methods

| Method | Signal | Confidence |
|--------|--------|------------|
| **Explicit statement** | "I'm 34" / "My daughter is 4" | Very high |
| **Voice analysis** | Pitch, cadence, vocabulary complexity | Medium |
| **Vocabulary analysis** | Word choice, sentence structure | Medium |
| **Behavioral patterns** | Topics, interaction style | Low |
| **User/parent setup** | Parent configures child's profile | Very high |
| **Conversational onboarding** | Atlas asks naturally | High |

**Important**: Atlas never assumes age. It starts at `unknown` (neutral responses) and refines over time.

### Response Profiles

#### Toddler (ages 2-4)

```yaml
tone: warm, encouraging, simple
vocabulary: basic (< 500 common words)
sentence_length: 5-8 words max
features:
  - Use simple, concrete language
  - Positive reinforcement ("Great question!")
  - Sound effects and fun language when appropriate
  - Never use sarcasm or irony
  - Device responses: simple confirmations with fun touches
  - Safety: never provide information a toddler shouldn't have
  
examples:
  greeting: "Hi Emma! 👋"
  lights_off: "All done! Lights are sleeping now. 🌙"
  weather: "It's sunny outside! ☀️ Perfect for playing!"
  unknown: "Hmm, I'm not sure about that. Let's ask a grown-up!"
```

#### Child (ages 5-11)

```yaml
tone: friendly, patient, encouraging curiosity
vocabulary: age-appropriate, willing to explain new words
sentence_length: 10-15 words
features:
  - Encourage questions and curiosity
  - Explain things simply but don't talk down
  - Use analogies to familiar things
  - Gently correct misconceptions
  - Device responses: slightly playful
  - Safety: filter inappropriate content, redirect gently
  
examples:
  greeting: "Hey there, what's up?"
  lights_off: "Done — lights are off in your room!"
  weather: "It's 72 degrees and sunny — great day to be outside!"
  explain: "A router is like a mail sorter for the internet — 
            it makes sure the right information gets to the right device."
```

#### Teenager (ages 12-17)

```yaml
tone: casual, respectful, not condescending
vocabulary: full range, can use slang naturally
sentence_length: natural
features:
  - Don't try too hard to be "cool" — teens detect that instantly
  - Direct, honest answers
  - Respect their intelligence
  - Appropriate humor (not forced)
  - Device responses: brief and efficient
  - Safety: filter extreme content, but treat them as capable
  
examples:
  greeting: "Hey, what's up?"
  lights_off: "Done."
  weather: "72 and sunny. Nice."
  explain: "Basically, a VPN encrypts your traffic so your ISP 
            can't see what you're doing. Think of it as a private tunnel."
```

#### Adult (18+)

```yaml
tone: matches user's emotional profile (casual → casual, formal → formal)
vocabulary: full technical vocabulary for technical users
sentence_length: adaptive to user's style
features:
  - Full personality expression
  - Humor matching user's style
  - Technical depth as needed
  - Proactive suggestions
  - Device responses: contextual and smart
  
examples:
  # These are further personalized by emotional_profiles
  greeting_casual: "Hey Derek, what's going on?"
  greeting_formal: "Good evening. How can I help?"
  lights_off: "Done — office lights off."
  explain: "The MoE architecture activates only 3B of the 30B 
            parameters per token, giving you the reasoning capacity 
            of a much larger model at the inference cost of a small one."
```

#### Unknown (default)

```yaml
tone: neutral-friendly, middle ground
vocabulary: moderate, avoids overly technical or overly simple
sentence_length: 10-15 words
features:
  - Pleasant and helpful without assuming anything
  - No age-specific humor or references
  - Slightly more formal than casual
  - Will naturally probe for more context through conversation
  
examples:
  greeting: "Hello! How can I help you?"
  lights_off: "Done — the lights are off."
  weather: "It's currently 72°F and sunny."
```

---

## Conversational Onboarding

When Atlas encounters a new user (no profile exists), it behaves like meeting someone for the first time — curious, polite, building rapport naturally.

### First Encounter Flow

```
Atlas detects: new user_id with no profile OR unknown voice

Atlas: "Hey there! I don't think we've met — I'm Atlas. What's your name?"
User: "I'm Sarah"
→ COLD: store {user_id, display_name: "Sarah", source: "onboarding"}

Atlas: "Nice to meet you, Sarah! I help out around the house — 
        lights, temperature, music, questions, whatever you need."

[Later in conversation, naturally:]
Atlas: "By the way, is there anything you'd like me to know about 
        how you prefer things? Like, some people want short answers, 
        others like details."
User: "Keep it brief"
→ COLD: store {preference: "brief responses", communication_style: "concise"}
```

### Returning User — "We've Talked Before"

```
Atlas: "Hey! I don't think we've met..."
User: "Actually, we've talked before. I'm Derek."

Atlas checks:
  1. HOT query: "Derek" → finds existing profile
  2. If voice: compare embedding to Derek's stored profile
  3. If match: link this session/voice to existing profile

Atlas: "Oh, Derek! Right, sorry about that. Welcome back. 
        [If voice changed:] Your voice sounded a bit different — 
        want me to update my voice profile for you?"

→ COLD: append voice sample to improve embedding (never overwrite)
→ COLD: store {note: "had trouble recognizing Derek's voice on 2026-02-27"}
```

### Gradual Profile Building

Atlas doesn't interrogate users. It learns passively from conversations and occasionally asks naturally:

```
After 5+ interactions, no age info:
  Atlas: "Hey Sarah, just curious — should I keep things simple 
          or are you good with technical details? I want to make 
          sure I'm explaining things the right way."

After user mentions a child:
  User: "My daughter keeps asking about the weather"
  Atlas: "How old is she? I can adjust how I talk to her if 
          she ever chats with me directly."
  User: "She's 4"
  → COLD: store {fact: "Sarah has a daughter, age 4"}
  → COLD: store to daughter's profile (if identified): {age: 4, age_group: "toddler"}
```

---

## Profile Evolution — Append-Only with Versioning

### Why Never Overwrite?

1. **Corrections are data** — knowing what changed tells you about the user
2. **Historical context** — "you used to prefer X, now you prefer Y" 
3. **Confidence building** — more data points = better understanding
4. **Mistake recovery** — can always roll back to earlier understanding

### Versioning Model

```
Profile Entry #1: { text: "Derek is 33", type: "fact", ts: "2026-01-15", confidence: 0.9 }
Profile Entry #2: { text: "Derek is 34", type: "correction", supersedes: "#1", 
                     ts: "2026-03-15", confidence: 0.95, 
                     note: "birthday passed, age updated" }
Profile Entry #3: { text: "Derek's birthday is March 15", type: "fact_derived",
                     derived_from: ["#1", "#2"], ts: "2026-03-15", confidence: 0.8 }
```

The HOT path always returns the **latest non-superseded** entry. The nightly evolution job can consolidate old chains into summary entries.

### Confidence Scoring

| Source | Base Confidence |
|--------|----------------|
| User explicitly stated | 0.95 |
| Parent/admin configured | 0.95 |
| Derived from conversation | 0.7 |
| Voice analysis inference | 0.5 |
| Behavioral inference | 0.4 |
| System default | 0.3 |

Confidence increases with corroboration:
```
Entry: "Derek is technical" (confidence: 0.4, source: behavioral)
Entry: "Derek asked about Docker internals" (confidence: 0.4, source: behavioral)
Entry: "Derek said 'I'm a systems engineer'" (confidence: 0.95, source: explicit)
→ Nightly consolidation: "Derek is technical" (confidence: 0.95, corroborated 3x)
```

---

## Voice-Based Age Estimation

When speaker-id processes audio, it can extract secondary features:

```python
# From the same audio used for speaker identification:
features = {
    "pitch_mean": 220.0,       # Hz — higher for children
    "pitch_variance": 45.0,    # More variable for younger speakers
    "speech_rate": 3.2,        # syllables/sec — slower for young children
    "vocabulary_complexity": 0.4,  # 0-1 score from transcript analysis
}

# Age estimation heuristics:
if pitch_mean > 300 and speech_rate < 2.5:
    estimated_age_group = "toddler"  # confidence: 0.5
elif pitch_mean > 250 and vocabulary_complexity < 0.5:
    estimated_age_group = "child"    # confidence: 0.5
elif pitch_mean > 200 and vocabulary_complexity < 0.7:
    estimated_age_group = "teen"     # confidence: 0.4
else:
    estimated_age_group = "adult"    # confidence: 0.4
```

**Important**: Voice estimation is low confidence. It's a **hint**, not a determination. Atlas uses it to start with an appropriate default tone, then refines through interaction.

---

## SQLite User Profile Table

For fast structured queries (age group filtering, active user lookup):

```sql
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    age INTEGER,                    -- actual age (null if unknown)
    age_group TEXT DEFAULT 'unknown', -- toddler, child, teen, adult, unknown
    age_confidence REAL DEFAULT 0.0, -- 0.0 - 1.0
    vocabulary_level TEXT DEFAULT 'moderate',
    preferred_tone TEXT DEFAULT 'neutral',
    communication_style TEXT DEFAULT 'moderate',
    humor_style TEXT,
    is_parent BOOLEAN DEFAULT FALSE, -- has children in the system
    parent_user_id TEXT,            -- if this is a child, who's their parent
    onboarding_complete BOOLEAN DEFAULT FALSE,
    profile_version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_user_id) REFERENCES user_profiles(user_id)
);

CREATE INDEX idx_profiles_age_group ON user_profiles(age_group);
```

### Parental Controls

When a user is identified as a child (age_group: toddler/child/teen):

```sql
CREATE TABLE parental_controls (
    child_user_id TEXT PRIMARY KEY,
    parent_user_id TEXT NOT NULL,
    content_filter_level TEXT DEFAULT 'strict', -- strict, moderate, relaxed
    allowed_devices TEXT DEFAULT '[]',          -- JSON: which HA entities they can control
    allowed_hours TEXT DEFAULT '{}',            -- JSON: {"start": "07:00", "end": "21:00"}
    require_parent_for TEXT DEFAULT '[]',       -- JSON: ["lock", "climate", "alarm"]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (child_user_id) REFERENCES user_profiles(user_id),
    FOREIGN KEY (parent_user_id) REFERENCES user_profiles(user_id)
);
```

Example: 4-year-old Emma can turn her bedroom light on/off but can't unlock the front door or change the thermostat.
