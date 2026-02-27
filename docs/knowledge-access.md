# Atlas Cortex — Knowledge Access & Data Privacy

## Overview

Atlas can access the household's files, messages, documents, photos, calendars, and other personal data to provide truly contextual assistance. But with that access comes strict responsibility: **data is scoped to the user who owns it**. Atlas never leaks one person's private data to another, even within the same household.

---

## Data Sources

Atlas can index and search across:

| Source | Type | Example Uses |
|--------|------|-------------|
| **Nextcloud** | Files, photos, calendars, contacts | "Where's that PDF I downloaded last week?" |
| **Text messages** (via HA/phone integration) | Conversations | "What time did Sarah say she'd be home?" |
| **Email** (IMAP) | Inbox, sent, drafts | "Did I get a shipping notification?" |
| **Notes** (Nextcloud/Obsidian) | Markdown, text | "What were my notes from the meeting?" |
| **Calendar** (CalDAV) | Events, reminders | "What's on my schedule tomorrow?" |
| **Photos** (Nextcloud) | Images with metadata | "Show me photos from last Christmas" |
| **Documents** (NAS shares) | PDFs, docs, spreadsheets | "Find the tax document from 2025" |
| **Bookmarks/history** | URLs, titles | "What was that article I was reading about Docker?" |
| **HA history** | Device states, automations | "When did the garage door last open?" |
| **Chat history** | Prior Atlas conversations | "What did we talk about yesterday?" |

---

## Privacy Model: User-Scoped Data Access

### Core Rule

> **Atlas only shares data with the user who owns it.**

Every piece of indexed data has an `owner_id`. When Atlas retrieves information, it filters by the requesting user's identity. No exceptions.

```
Derek asks: "What did Sarah text me?"
→ Atlas checks: requester = Derek
→ Searches Derek's text messages (owner_id = derek)
→ Returns messages FROM Sarah TO Derek ✓
→ Does NOT access Sarah's private messages ✗

Sarah asks: "What did Derek text me?"
→ Atlas checks: requester = Sarah
→ Searches Sarah's text messages (owner_id = sarah)
→ Returns messages FROM Derek TO Sarah ✓
→ Does NOT access Derek's private messages ✗
```

### Access Levels

```
┌─────────────────────────────────────────────────────────┐
│                  Data Access Hierarchy                    │
│                                                          │
│  Level 1: PRIVATE (default)                              │
│    Owner: single user                                    │
│    Access: only that user can query this data             │
│    Examples: text messages, email, personal notes,        │
│              browsing history, private files               │
│                                                          │
│  Level 2: SHARED (explicit opt-in)                       │
│    Owner: user who shared it                             │
│    Access: specified users or "household"                 │
│    Examples: shared calendar, family photo album,         │
│              household shopping list, shared notes         │
│                                                          │
│  Level 3: HOUSEHOLD (visible to all members)             │
│    Owner: system / household                             │
│    Access: all identified household members               │
│    Examples: HA device states, house rules,               │
│              shared recipes, grocery list                  │
│                                                          │
│  Level 4: PUBLIC (no auth required)                      │
│    Owner: system                                         │
│    Access: anyone, including unidentified voices          │
│    Examples: time, weather, general knowledge,            │
│              house-wide announcements                      │
└─────────────────────────────────────────────────────────┘
```

### Enforcement in the Pipeline

```python
# Every data query goes through the access gate
def query_knowledge(query_text, requester_user_id, requester_confidence):
    """
    requester_confidence: how sure we are of the user's identity
      - 0.95+: verified login or high-confidence voice match
      - 0.7-0.95: probable voice match
      - < 0.7: uncertain identity
    """
    
    # Determine access level based on identity confidence
    if requester_confidence >= 0.85:
        # Verified user: can access PRIVATE + SHARED + HOUSEHOLD + PUBLIC
        access_levels = ['private', 'shared', 'household', 'public']
        owner_filter = requester_user_id
    elif requester_confidence >= 0.5:
        # Probable user: SHARED + HOUSEHOLD + PUBLIC only (no private)
        access_levels = ['shared', 'household', 'public']
        owner_filter = requester_user_id
    else:
        # Unknown identity: HOUSEHOLD + PUBLIC only
        access_levels = ['household', 'public']
        owner_filter = None
    
    results = knowledge_store.search(
        query=query_text,
        owner_id=owner_filter,
        access_levels=access_levels,
    )
    
    return results
```

**Key behavior**: If Atlas isn't sure who's talking (low speaker confidence), it defaults to household/public data only. It never risks exposing private data to an unverified user.

### What Happens When Someone Asks for Another Person's Data

```
Guest: "What are Derek's text messages?"
Atlas: "I can't share someone else's private messages. 
        Is there something else I can help with?"

Derek's kid: "What did mom text dad?"
Atlas: "Those are private messages between your parents. 
        I can't share those. Need help with something else?"

Derek: "What did Sarah text me about dinner?"
Atlas: [verified Derek] → searches Derek's messages
       "Sarah said she'd be home by 7 and asked you to 
        start the rice."
```

---

## Knowledge Index Architecture

### Indexing Pipeline

```
┌──────────────────────────────────────────────────────────┐
│                  Knowledge Indexer (Nightly + On-Demand)   │
│                                                           │
│  Source Connectors:                                       │
│    Nextcloud (WebDAV) ─┐                                 │
│    IMAP (email) ───────┤                                 │
│    CalDAV (calendar) ──┤                                 │
│    SMB/NFS (NAS) ──────┤──▶ Document Processor            │
│    HA API (history) ───┤      │                          │
│    Chat history (DB) ──┘      ├── Extract text            │
│                               ├── Extract metadata        │
│                               ├── Assign owner_id         │
│                               ├── Assign access_level     │
│                               ├── PII tag (don't redact   │
│                               │   — this IS the user's    │
│                               │   data, just tag it)      │
│                               └── Chunk if large          │
│                                       │                   │
│                                       ▼                   │
│                              ┌─────────────────┐         │
│                              │  Embed (Ollama)  │         │
│                              │  nomic-embed-text│         │
│                              └────────┬────────┘         │
│                                       │                   │
│                                       ▼                   │
│                              ┌─────────────────┐         │
│                              │  ChromaDB        │         │
│                              │  collection:     │         │
│                              │  cortex_knowledge│         │
│                              └─────────────────┘         │
│                                       +                   │
│                              ┌─────────────────┐         │
│                              │  SQLite FTS5     │         │
│                              │  knowledge_fts   │         │
│                              └─────────────────┘         │
└──────────────────────────────────────────────────────────┘
```

### Knowledge Document Schema

```python
# ChromaDB collection: cortex_knowledge
{
    "id": "sha256(source|path|owner_id|chunk_index)",
    "embedding": [0.123, ...],              # 768-dim
    "document": "Meeting notes: discussed migration to...",  # text content
    "metadata": {
        "owner_id": "derek",                # who owns this data
        "access_level": "private",          # private | shared | household | public
        "shared_with": [],                  # user_ids if access_level = shared
        "source": "nextcloud",              # nextcloud, email, sms, calendar, ha, chat
        "source_path": "/Documents/notes/meeting-2026-02-20.md",
        "content_type": "text/markdown",
        "title": "Meeting Notes — Feb 20",
        "created_at": "2026-02-20T14:00:00Z",
        "modified_at": "2026-02-20T15:30:00Z",
        "chunk_index": 0,                   # for large documents split into chunks
        "total_chunks": 1,
        "tags": ["meeting", "work"],
        "pii_detected": false,
        "indexed_at": "2026-02-21T03:00:00Z"
    }
}
```

### SQLite FTS5 Mirror

```sql
CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    doc_id,
    owner_id,
    access_level,
    source,
    title,
    text,
    tags,
    tokenize='porter unicode61'
);
```

### SQLite Metadata Table

```sql
CREATE TABLE knowledge_docs (
    doc_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    access_level TEXT NOT NULL DEFAULT 'private',
    shared_with TEXT DEFAULT '[]',      -- JSON array of user_ids
    source TEXT NOT NULL,
    source_path TEXT,
    content_type TEXT,
    title TEXT,
    chunk_index INTEGER DEFAULT 0,
    total_chunks INTEGER DEFAULT 1,
    content_hash TEXT,                  -- for change detection
    created_at TIMESTAMP,
    modified_at TIMESTAMP,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_knowledge_owner ON knowledge_docs(owner_id);
CREATE INDEX idx_knowledge_access ON knowledge_docs(access_level);
CREATE INDEX idx_knowledge_source ON knowledge_docs(source);
```

---

## Retrieval Flow

When Atlas needs to reference files/data to answer a question:

```
User (Derek, verified): "What was in that email about the server parts?"

1. Access gate: Derek verified (confidence 0.95)
   → Can access: private + shared + household + public

2. Knowledge HOT query:
   → Embed query via Ollama
   → ChromaDB vector search (filtered: owner_id=derek OR access_level IN (shared, household, public))
   → FTS5 BM25 search (same filter)
   → RRF fusion → top results

3. Results:
   [
     { title: "Re: Server Parts Order", source: "email", 
       text: "Your order of 128GB DDR4 ECC has shipped...", 
       access_level: "private", owner: "derek", score: 0.92 }
   ]

4. Atlas responds:
   "You got a shipping confirmation — your 128GB DDR4 ECC order 
    has shipped. Want me to pull up the tracking number?"
```

---

## Source Connectors

### Nextcloud (WebDAV)
```python
# Connect to Derek's Nextcloud via WebDAV
# Scan for new/modified files since last index
# Supported: .txt, .md, .pdf, .docx, .xlsx, .csv, .json
# Photos: index EXIF metadata (date, location, camera) — not pixel content
# Owner: derived from Nextcloud username → mapped to Atlas user_id
```

### Email (IMAP)
```python
# Connect via IMAP (local mail server or forwarded)
# Index: subject, from, to, body text, attachment names
# Owner: the mailbox owner
# Access: always PRIVATE
# PII tagging: emails inherently contain PII — tag, don't redact
```

### Text Messages (via HA or phone bridge)
```python
# If user has phone integration (e.g., HA companion app, Matrix bridge)
# Index: message text, sender, recipient, timestamp
# Owner: the user whose phone it is
# CRITICAL: messages are PRIVATE to the phone owner
# Atlas can reference "Sarah texted you..." but never "Derek texted Sarah..."
#   (unless Sarah asks about messages TO her FROM Derek)
```

### Calendar (CalDAV)
```python
# Connect to CalDAV (Nextcloud calendar, Google via bridge)
# Index: event title, description, start/end, location, attendees
# Shared calendars: access_level = 'shared', shared_with = attendee list
# Private calendars: access_level = 'private'
```

### NAS Files (SMB/NFS)
```python
# Scan configured shares
# Respect filesystem permissions where possible
# Default: files in /derek/ → owner: derek, access: private
# Files in /shared/ → access: household
# Supported: text, PDF, office docs, config files
```

### HA Device History
```python
# Query HA long-term statistics API
# Owner: household (all members can ask about device states)
# "When did the garage door last open?" → accessible to all
# Security-sensitive: alarm codes, lock PINs → NOT indexed
```

---

## What Atlas Does NOT Index

| Data Type | Reason |
|-----------|--------|
| Passwords / credentials | Security — never stored in knowledge base |
| Alarm codes / PINs | Security |
| Financial account details | PII risk too high |
| Medical records | Privacy regulations |
| Audio/video raw files | Too large, privacy-sensitive |
| Encrypted files | Can't read them, shouldn't try |
| `.env` files, SSH keys | Secrets |

---

## Children's Data Protection

For users with `age_group` of toddler/child/teen:

- Their data is **also visible to their parent** (via `parental_controls`)
- They **cannot access** parent's private data
- Their search results are **content-filtered** by age group
- Atlas will not help a child access content above their age level:
  ```
  Kid: "Show me dad's emails"
  Atlas: "I can't show you someone else's emails. 
          Need help with your own stuff?"
  ```

---

## Data Freshness & Sync

| Source | Sync Frequency | Method |
|--------|---------------|--------|
| Calendar | Every 15 minutes | CalDAV poll |
| HA device states | Real-time | WebSocket subscription |
| Email | Every 30 minutes | IMAP IDLE or poll |
| Text messages | Real-time (if bridge supports) | Push notification |
| Nextcloud files | Nightly + on-demand | WebDAV scan for changes |
| NAS files | Nightly | File modification time scan |
| Chat history | Real-time | Logged by interaction logger |

### On-Demand Reindex
```
User: "I just saved a file in Nextcloud, can you find it?"
Atlas: "Let me check... [triggers on-demand scan of Nextcloud] 
        Found it — 'server-config.md', uploaded 2 minutes ago. 
        What do you need from it?"
```

---

## Integration with Existing Systems

### Memory System (C5)
Knowledge and memory are separate but complementary:
- **Memory**: things Atlas learned from conversations (preferences, facts about the user)
- **Knowledge**: the user's actual files, messages, and documents
- Both feed into the HOT path and are searchable together
- Both respect the same access level filtering

### Grounding System
Knowledge access is a **grounding source** — when Atlas isn't sure about something the user mentioned previously, it can check their files:
```
"You mentioned a Docker config issue last week — let me check 
 your notes... yeah, in your server-config.md you have 
 port 8080 mapped twice. That's probably the conflict."
```

### Nightly Evolution
The knowledge indexer runs as part of the nightly job:
- Scan all sources for new/modified content
- Re-embed changed documents
- Purge deleted documents from index
- Report: "Indexed 47 new documents, 12 modified, 3 deleted"
