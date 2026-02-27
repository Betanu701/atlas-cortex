# Atlas Cortex — Lists & Shared Data Management

## Overview

Lists are one of the most common household interactions — grocery lists, to-do lists, shopping lists, wish lists, chore lists. Atlas needs to handle them seamlessly across **multiple backends**, respect **per-list permissions**, and **never make the user repeat themselves** when context is ambiguous.

---

## List Sources

Lists live in different places depending on what the user has set up:

| Source | Examples | Access Method |
|--------|----------|---------------|
| **Home Assistant** | Shopping list, to-do lists, checklists | HA REST API (`/api/services/todo/`) |
| **Nextcloud** | Tasks (CalDAV), Deck boards | CalDAV / Nextcloud API |
| **Grocery apps** | AnyList, OurGroceries, Bring!, Grocy | App-specific API or integration |
| **Todoist / TickTick** | Personal tasks, shared projects | REST API |
| **Plain text / Markdown** | `grocery.md`, `todo.txt` on NAS | File access via NAS/Nextcloud |
| **Open WebUI notes** | In-chat lists | Open WebUI API |

Atlas abstracts over all of these — the user says "add milk to the grocery list" and Atlas figures out where the grocery list actually lives.

---

## List Registry

Atlas maintains a registry of known lists, their backends, and their permissions:

```sql
CREATE TABLE list_registry (
    id TEXT PRIMARY KEY,                -- "grocery", "christmas-2026", "chores"
    display_name TEXT NOT NULL,         -- "Grocery List", "Christmas Shopping"
    backend TEXT NOT NULL,              -- "ha_todo", "nextcloud_caldav", "grocy", "file", "todoist"
    backend_config TEXT NOT NULL,       -- JSON: connection details (entity_id, URL, path, etc.)
    owner_id TEXT NOT NULL,             -- who created / owns the list
    access_level TEXT DEFAULT 'private', -- "public", "household", "shared", "private"
    shared_with TEXT DEFAULT '[]',      -- JSON: user_ids (when access_level = "shared")
    can_add TEXT DEFAULT '[]',          -- JSON: user_ids who can add items (or ["*"] for anyone)
    can_view TEXT DEFAULT '[]',         -- JSON: user_ids who can view (or ["*"] for anyone)
    can_remove TEXT DEFAULT '[]',       -- JSON: user_ids who can remove items
    aliases TEXT DEFAULT '[]',          -- JSON: ["groceries", "shopping", "food list"]
    category TEXT,                      -- "grocery", "todo", "shopping", "chores", "wishlist"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP
);

CREATE INDEX idx_lists_owner ON list_registry(owner_id);
CREATE INDEX idx_lists_category ON list_registry(category);
```

### Permission Model

```
┌─────────────────────────────────────────────────────────┐
│                List Permission Levels                    │
│                                                          │
│  PUBLIC (access_level = "public")                       │
│    • Anyone can add items, including unknown voices      │
│    • Anyone can view                                     │
│    • Only owner + designated users can remove            │
│    • Use case: grocery list, household chores            │
│                                                          │
│  HOUSEHOLD (access_level = "household")                 │
│    • All identified household members can add/view       │
│    • Unknown voices cannot modify                        │
│    • Use case: family to-do list, meal planning          │
│                                                          │
│  SHARED (access_level = "shared")                       │
│    • Specific users listed in shared_with                │
│    • can_add / can_view / can_remove per user            │
│    • Use case: christmas list (view-only for kids)       │
│    • Use case: shared project with specific people       │
│                                                          │
│  PRIVATE (access_level = "private")                     │
│    • Only owner can add/view/remove                      │
│    • Use case: personal wish list, private to-do         │
└─────────────────────────────────────────────────────────┘
```

### Example Configurations

```json
// Grocery list — anyone can add, public
{
    "id": "grocery",
    "display_name": "Grocery List",
    "backend": "ha_todo",
    "backend_config": {"entity_id": "todo.grocery_list"},
    "owner_id": "derek",
    "access_level": "public",
    "can_add": ["*"],
    "can_view": ["*"],
    "can_remove": ["derek", "sarah"],
    "aliases": ["groceries", "shopping list", "food list", "the list"],
    "category": "grocery"
}

// Christmas shopping — Derek and Sarah can edit, kids can't even see it
{
    "id": "christmas-2026",
    "display_name": "Christmas Shopping 2026",
    "backend": "nextcloud_caldav",
    "backend_config": {"calendar_url": "..."},
    "owner_id": "sarah",
    "access_level": "shared",
    "shared_with": ["derek", "sarah"],
    "can_add": ["derek", "sarah"],
    "can_view": ["derek", "sarah"],
    "can_remove": ["derek", "sarah"],
    "aliases": ["christmas list", "xmas shopping", "gift list"],
    "category": "shopping"
}

// Emma's chore chart — Emma can view, parents can edit
{
    "id": "emma-chores",
    "display_name": "Emma's Chores",
    "backend": "ha_todo",
    "backend_config": {"entity_id": "todo.emma_chores"},
    "owner_id": "derek",
    "access_level": "shared",
    "shared_with": ["derek", "sarah", "emma"],
    "can_add": ["derek", "sarah"],
    "can_view": ["derek", "sarah", "emma"],
    "can_remove": ["derek", "sarah"],
    "aliases": ["emma's chores", "chore chart"],
    "category": "chores"
}
```

---

## List Resolution — "Which List?"

When a user says "add milk to the list", Atlas needs to figure out *which* list. Resolution order:

### Step 1: Explicit Name Match
```
"Add milk to the grocery list"
→ Match "grocery list" against display_name + aliases
→ Found: grocery list ✓
```

### Step 2: Category Inference
```
"Add milk"  (no list specified)
→ "milk" is a food item → category = "grocery"
→ Find lists where category = "grocery" AND user has add permission
→ Found: grocery list ✓
```

### Step 3: Recent Context
```
User was just talking about a list 30 seconds ago:
  "What's on the grocery list?" → [shows list]
  "Add bread"
→ Conversation context: last referenced list = grocery
→ Add to grocery list ✓
```

### Step 4: User Preference Memory
```
From memory: "Derek usually means the HA grocery list when he says 'the list'"
→ Route to grocery list ✓
```

### Step 5: Ask (only as last resort, and remember the answer)
```
"Add new batteries"
→ Could be grocery, could be hardware shopping, could be to-do
→ Atlas: "Which list should I add batteries to? I've got:
          • Grocery List
          • Hardware Shopping
          • General To-Do"
→ User: "Hardware"
→ COLD memory: "When Derek says 'add batteries', route to hardware shopping list"
→ Next time: no need to ask
```

**Critical: Atlas remembers the answer.** The user should never have to clarify the same ambiguity twice.

### Resolution Flow

```python
def resolve_list(user_message, user_id, conversation_context):
    # 1. Check for explicit list name in the message
    list_match = match_list_by_name(user_message, user_id)
    if list_match:
        return list_match
    
    # 2. Infer category from item content
    item = extract_item(user_message)
    category = classify_item_category(item)  # "milk" → grocery
    if category:
        lists = find_lists_by_category(category, user_id)
        if len(lists) == 1:
            return lists[0]
    
    # 3. Check recent conversation context
    recent_list = conversation_context.get('last_referenced_list')
    if recent_list and user_has_access(recent_list, user_id, 'add'):
        return recent_list
    
    # 4. Check memory for user preference
    memory_hit = memory_hot_query(f"which list for {item}", user_id)
    if memory_hit and memory_hit.confidence > 0.7:
        return memory_hit.list_id
    
    # 5. Ask the user (and remember)
    available_lists = get_accessible_lists(user_id, permission='add')
    return ask_user_which_list(item, available_lists)
    # → When they answer, store preference in COLD memory
```

---

## Backend Adapters

Each list backend has an adapter that implements a common interface:

```python
class ListAdapter:
    def get_items(self, list_config) -> list[ListItem]:
        """Retrieve all items from the list."""
    
    def add_item(self, list_config, item: str) -> bool:
        """Add an item to the list."""
    
    def remove_item(self, list_config, item_id: str) -> bool:
        """Remove/complete an item."""
    
    def check_item(self, list_config, item_id: str) -> bool:
        """Mark an item as done/checked."""
```

### Adapter: Home Assistant To-Do
```python
# POST /api/services/todo/add_item
# {"entity_id": "todo.grocery_list", "item": "Milk"}

# POST /api/services/todo/remove_item  
# {"entity_id": "todo.grocery_list", "item": "Milk"}

# GET /api/states/todo.grocery_list
# → state attributes contain item list
```

### Adapter: Nextcloud CalDAV
```python
# VTODO items via CalDAV protocol
# Create: PUT with VTODO component
# List: REPORT with calendar-query
```

### Adapter: File-Based
```python
# Read/write to a text file on NAS
# Format: one item per line, "- [ ] item" for unchecked
# Supports markdown checkbox format
```

### Adapter: Grocy / OurGroceries / etc.
```python
# App-specific REST API
# Configured per-list in backend_config
```

---

## Natural Language Interactions

Atlas handles a wide range of list-related requests:

```
Adding:
  "Add milk to the grocery list"
  "We need paper towels"           → infer grocery
  "Put 'fix garage light' on the to-do"
  "Remind me to buy batteries"     → ask which list or infer

Removing:
  "Take milk off the grocery list"
  "I got the paper towels"         → mark as done/remove
  "Cross off everything under produce"

Viewing:
  "What's on the grocery list?"
  "Read me the to-do list"
  "What do we need from the store?"

Checking:
  "Mark 'mow lawn' as done"
  "I did the dishes"               → match to chore list item

Sharing:
  "Make the grocery list public"
  "Don't let the kids see the christmas list"
  "Let Sarah edit the meal plan"
```

---

## Permission Enforcement Examples

```
Unknown voice: "Add milk to the grocery list"
→ Grocery list is PUBLIC (can_add: ["*"])
→ ✓ Added. "Got it — milk added to the grocery list."

Unknown voice: "What's on the christmas list?"
→ Christmas list is SHARED (shared_with: ["derek", "sarah"])
→ Speaker not identified as derek or sarah
→ ✗ "I can't share that list — it's private."

Emma (age 4): "Add cookies to the list"
→ "the list" → resolve: grocery list (PUBLIC, can_add: ["*"])
→ ✓ "Cookies added to the grocery list! 🍪"

Emma: "What's on mom and dad's christmas list?"
→ Christmas list: shared_with doesn't include emma
→ ✗ "That's a surprise list — I can't tell you what's on it! 😄"
```

---

## List Discovery

During the nightly job or on first setup, Atlas discovers lists from connected services:

```
HA Discovery:
  GET /api/states → filter entities with domain "todo"
  → todo.grocery_list, todo.general_tasks, todo.emma_chores
  → Auto-register in list_registry with owner = admin, access = household

Nextcloud Discovery:
  PROPFIND on CalDAV endpoint → find VTODO calendars
  → Auto-register with owner from Nextcloud username

File Discovery:
  Scan configured paths for known list patterns
  → *.todo, *.list, todo.txt, grocery.md
  → Auto-register with owner from file path
```

The user can then customize permissions via voice or chat:
```
"Make the grocery list public"
"Only let me and Sarah see the christmas list"
```

---

## Integration with Existing Systems

### Memory (C5)
- List preferences stored: "Derek usually means grocery when he says 'the list'"
- Item routing patterns learned: "batteries → hardware shopping"
- Never re-ask a resolved ambiguity

### Knowledge Access (C8)
- List contents are queryable as knowledge: "Did I already add milk?"
- Lists indexed with proper access levels from list_registry

### Layer 2 (Direct Commands)
- List operations are ideal Layer 2 candidates — no LLM needed
- Pattern: "add X to Y list" → regex → adapter → done in ~100ms
- Learned patterns from fallthrough: "we need X" → grocery list
