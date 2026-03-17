# Two-Phase Self-Evolution: How an AI Modifies Its Own Code on 8GB of VRAM

> **TL;DR:** Split self-modification into two phases: a "thinker" LLM creates a detailed
> surgical plan, then it unloads and a "typist" coding LLM loads to execute the plan.
> Neither model needs to do both jobs. This enables self-evolving AI on a single 8GB GPU.

---

## The Challenge

Self-evolving AI — code that can inspect, evaluate, and improve itself — sounds like
it requires massive compute. You need:

1. A model smart enough to **understand** the codebase and identify improvements
2. A model skilled enough to **write** the actual code changes
3. Enough VRAM to **run** these models

On cloud infrastructure, you'd just load both models (or one large model that does
both). On a consumer GPU with 8 GB of VRAM, you can't.

But here's the key insight: **these two capabilities don't need to run simultaneously.**

---

## The Two-Phase Architecture

### Phase 1: "The Thinker" — Core LLM Plans

The core LLM (small, general-purpose, always resident) analyzes its own behavior and
creates a structured modification plan:

```json
{
  "evolution_id": "evo-2026-03-12-001",
  "trigger": "response_quality_score < 0.7 for greeting patterns",
  "zone": "content/greetings.py",
  "analysis": "Current greeting responses are repetitive. The same 5 patterns cycle predictably after 3 days of use.",
  "plan": {
    "objective": "Add time-aware and context-aware greeting variations",
    "steps": [
      {
        "action": "add_function",
        "file": "cortex/content/greetings.py",
        "function_name": "get_contextual_greeting",
        "signature": "def get_contextual_greeting(time_of_day: str, last_greeting: str, user_mood: str) -> str",
        "description": "Returns a greeting that varies by time, avoids repeating the last greeting used, and adjusts tone based on detected user mood",
        "test_cases": [
          {"input": {"time_of_day": "morning", "last_greeting": "Good morning!", "user_mood": "neutral"}, "expected_contains": ["morning", "day"]},
          {"input": {"time_of_day": "evening", "last_greeting": "Hey there", "user_mood": "tired"}, "expected_not_contains": ["excited", "energetic"]}
        ]
      },
      {
        "action": "modify_function",
        "file": "cortex/content/greetings.py",
        "function_name": "select_greeting",
        "change": "Replace random.choice with call to get_contextual_greeting, passing pipeline context"
      }
    ],
    "rollback": "git revert to pre-evolution commit",
    "safety_check": "Run full greeting test suite + core principles battery"
  }
}
```

**Critical detail:** The plan is detailed enough that the coding model doesn't need to
understand *why* — it just needs to translate structured instructions into Python code.
The thinker provides function signatures, test cases, and behavioral descriptions.

### The Swap (~2-3 seconds)

```
[Core LLM unloads from VRAM] → [Coding LLM loads into VRAM]
         ~1-2s                         ~1-2s
```

The evolution plan is saved to disk as JSON. No information is lost in the swap.

### Phase 2: "The Typist" — Coding LLM Executes

A specialized coding model (distilled to 5-6 GB) loads and executes each step:

```python
async def execute_evolution_plan(plan: EvolutionPlan):
    """Coding model executes the thinker's plan step by step."""
    
    for step in plan.steps:
        if step.action == "add_function":
            code = await coding_llm.generate(
                prompt=f"""Write a Python function with this exact signature:
                {step.signature}
                
                Behavior: {step.description}
                
                Test cases that must pass:
                {json.dumps(step.test_cases, indent=2)}
                
                Use only standard library imports. Follow existing code style."""
            )
            apply_code_change(step.file, code)
            
        elif step.action == "modify_function":
            existing = read_function(step.file, step.function_name)
            code = await coding_llm.generate(
                prompt=f"""Modify this existing function:
                ```python
                {existing}
                ```
                
                Required change: {step.change}
                Keep the same function signature. Preserve all existing behavior
                except what's explicitly being changed."""
            )
            apply_code_change(step.file, code)
    
    # Run tests
    test_results = await run_tests(plan.safety_check)
    
    if test_results.all_passed:
        git_commit(f"evolution: {plan.evolution_id} — {plan.objective}")
    else:
        git_revert()
        log_failure(plan.evolution_id, test_results)
```

The coding model doesn't need to understand Atlas's architecture. It just needs to:
1. Read the structured plan
2. Generate Python code matching the specs
3. Follow the test cases

This is precisely what coding models are optimized for.

---

## Why Two Phases Instead of One?

### Option A: One Large Model (Not Feasible on 8GB)

A model that can both reason about architecture AND write quality code needs to be
large — typically 14B+ parameters. At Q4 quantization, that's 8-10 GB. It won't
fit on an 8 GB GPU with overhead for KV cache and runtime.

### Option B: One Small Model (Poor Quality)

A sub-3B model can do basic code generation but struggles with:
- Understanding complex system architecture
- Identifying *what* should change and *why*
- Writing code that integrates well with existing patterns

### Option C: Two-Phase (Our Approach)

| Aspect | Thinker (Core LLM) | Typist (Coding LLM) |
|---|---|---|
| Size | Sub-1B active (pruned MoE) | 5-6 GB (distilled) |
| Strength | Reasoning, analysis, planning | Code generation, syntax |
| Weakness | Can't write production code | Doesn't understand architecture |
| Input | Codebase context, metrics | Structured JSON plan |
| Output | Detailed evolution plan | Working Python code |

Each model does what it's best at. The structured plan is the interface between them.

---

## Safety Architecture

Self-modifying code is dangerous. The safety architecture ensures evolution can never
break core functionality:

### Frozen Zones (Never Modified)

```python
FROZEN_ZONES = [
    "cortex/selfmod/",       # Can't modify its own evolution engine
    "cortex/safety/",        # Can't weaken safety checks
    "cortex/auth.py",        # Can't bypass authentication
    "cortex/notifications/", # Can't disable alerting
    "cortex/db.py",          # Can't corrupt data layer
]
```

### Guarded Zones (Require Admin Approval)

```python
GUARDED_ZONES = [
    "cortex/pipeline/",      # Core message processing
    "cortex/plugins/",       # Plugin behavior
    "cortex/integrations/",  # External service connections
]
```

### Open Zones (Auto-Apply After Tests Pass)

```python
OPEN_ZONES = [
    "cortex/content/",       # Response content and templates
    "cortex/filler/",        # Filler phrases
    "data/",                 # Data files
]
```

### The Test Battery

Every evolution must pass:

1. **Unit tests** — Does the changed code work in isolation?
2. **Integration tests** — Does it work with the rest of the system?
3. **Core principles test** — 100% pass rate on safety/values test suite
4. **Regression test** — No category scores decrease
5. **Personality test** — Does Atlas still sound like Atlas?

**If any test fails, the entire evolution is reverted.** No partial changes.

### Rate Limiting

- Maximum 3 evolutions per day
- Minimum 1 hour between evolutions
- Human admin can pause/resume at any time
- All changes tracked in a local git repository (`data/evolution/`)

---

## The Self-Evolution Loop

```
┌─────────────────────────────────────────────────┐
│                 Off-Hours (2-5 AM)               │
│                                                  │
│  1. Core LLM reviews recent interactions         │
│     - Which responses scored poorly?             │
│     - What patterns are repetitive?              │
│     - Where did users seem unsatisfied?          │
│                                                  │
│  2. Core LLM identifies improvement opportunity  │
│     - Checks zone permissions                    │
│     - Generates evolution plan (JSON)            │
│     - Saves plan to data/evolution/pending/      │
│                                                  │
│  3. MODEL SWAP (Core → Coder, ~2-3s)            │
│                                                  │
│  4. Coding LLM executes plan                     │
│     - Reads JSON plan                            │
│     - Generates code for each step               │
│     - Applies changes to codebase                │
│                                                  │
│  5. Test battery runs                            │
│     - All tests must pass                        │
│     - Core principles: 100% required             │
│     - No regression in any category              │
│                                                  │
│  6. If tests pass: git commit + promote          │
│     If tests fail: git revert + log failure      │
│                                                  │
│  7. MODEL SWAP (Coder → Core, ~2-3s)            │
│                                                  │
│  8. Core LLM verifies the evolution              │
│     - Reviews the diff                           │
│     - Runs a sanity check conversation           │
│     - Logs result to selfmod_log table           │
│                                                  │
│  ⚡ USER QUERY AT ANY POINT:                     │
│     → Abort evolution                            │
│     → Fast-swap to Core LLM if not loaded        │
│     → Preload TTS                                │
│     → Handle user first, resume later            │
└─────────────────────────────────────────────────┘
```

---

## Practical Considerations

### What Coding Model?

The best coding models for distillation as of March 2026:

| Model | Size | HumanEval | Notes |
|---|---|---|---|
| Qwen2.5-Coder-7B | 7B → distill to ~4B | 88.4% | Strong all-around |
| DeepSeek-Coder-V2-Lite | 16B MoE (2.4B active) | 90.2% | Already MoE, could prune further |
| Qwen3.5-4B | 4B dense | TBD | Latest gen, likely strong |

Target: distill to 5-6 GB GGUF so it fits on the 8 GB RTX 4060 with room for KV cache.

### Plan Granularity

The thinker's plan must be **extremely specific** — the typist is a skilled coder but
has zero context about Atlas. Each step should include:

- Exact file path
- Exact function signature (if adding a function)
- Behavioral description (what the code should do)
- Test cases (input/output examples)
- Integration point (where in the existing code this connects)

### Failure Recovery

If the coding model produces code that doesn't compile or pass tests:

1. **Retry once** with error message fed back to the coding model
2. If retry fails, **revert and log** the failure
3. The failure log is input to the next thinker session — the core LLM learns what plans
   the coding model struggles with and adjusts its planning approach

This creates a feedback loop that improves plan quality over time.

---

## What Makes This Novel

The idea of AI self-modification isn't new. But running it on **consumer hardware with
model swapping** is:

1. **Separation of concerns** — The thinker doesn't need to code. The coder doesn't need to reason about architecture. Each does its strength.

2. **Structured interface** — The JSON plan format means the two models don't need to be compatible or even from the same family. Any good coding model works as the typist.

3. **Hardware accessible** — This runs on a single $300 GPU. It doesn't require a cloud instance or a 48 GB A6000.

4. **Interruptible** — User queries always take priority. Self-evolution is a background process that gracefully yields.

5. **Safe by design** — Frozen zones, test batteries, rate limits, and automatic rollback make this safer than most human deployment pipelines.

---

## References

- [Atlas Cortex Self-Evolution Module](https://github.com/Betanu701/atlas-cortex) — `cortex/selfmod/`
- [Qwen2.5-Coder Technical Report](https://arxiv.org/abs/2409.12186) — Coding model benchmarks
- [DeepSeek-Coder-V2](https://arxiv.org/abs/2406.11931) — MoE coding model
- [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) — Prior art in autonomous AI agents
- [SWE-bench](https://www.swebench.com/) — Benchmark for AI code modification
- [Constitutional AI (Anthropic)](https://arxiv.org/abs/2212.08073) — Safety in AI self-improvement
