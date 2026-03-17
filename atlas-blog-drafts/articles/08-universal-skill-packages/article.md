# Universal Skill Packages: Coordinated LoRA Across the Entire Stack

## The Problem with Single-Model Fine-Tuning

Everyone fine-tunes their LLM. Some people fine-tune their TTS. Almost nobody
fine-tunes their STT. And absolutely nobody coordinates all three.

Here's what happens when you add a medical LoRA to your LLM but not your TTS:

```
User says: "What about metoprolol for my blood pressure?"

STT (no medical adapter):  "What about METO PRO LOL for my blood pressure?"
                                        ↑ wrong transcription
LLM (medical LoRA):        "Metoprolol is a beta-blocker commonly prescribed..."
                                        ↑ knows the drug, but got garbage input
TTS (no medical adapter):  "Met-oh-PRO-lol is a beta blocker..."
                                        ↑ wrong pronunciation
```

The LLM knows the right answer but got fed a bad transcription, then its correct
output got mispronounced. **Two out of three pipeline stages failed.** The user
hears garbled medical advice from a system that actually knows the right answer.

## The Solution: Skill Packages

A **skill package** is a coordinated set of LoRA adapters — one for each model in
the pipeline — that activate simultaneously when a domain is detected.

```
┌─────────────────────────────────────────────────┐
│                MEDICAL SKILL PACKAGE             │
│                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐│
│  │  STT LoRA    │  │  LLM LoRA    │  │ TTS LoRA ││
│  │  Whisper     │  │  Atlas Core  │  │ Orpheus   ││
│  │  ~30MB       │  │  ~80MB       │  │ ~30MB     ││
│  │              │  │              │  │           ││
│  │ Recognizes:  │  │ Knows:       │  │Pronounces:││
│  │ Drug names   │  │ Interactions │  │Drug names ││
│  │ Symptoms     │  │ Dosing       │  │Anatomy    ││
│  │ Anatomy      │  │ Anatomy      │  │Conditions ││
│  └──────────────┘  └──────────────┘  └──────────┘│
│                                                   │
│  Activation: ~1ms (LoRA merge)                   │
│  Total size: ~140MB                               │
│  Trigger: domain classifier detects medical topic │
└─────────────────────────────────────────────────┘
```

When the domain classifier detects a medical query, ALL three adapters activate
in parallel via `asyncio.gather()`:

```python
async def activate_skill(skill_name: str):
    skill = SKILL_REGISTRY[skill_name]
    await asyncio.gather(
        stt_engine.load_adapter(skill.stt_lora),
        llm_engine.load_adapter(skill.llm_lora),
        tts_engine.load_adapter(skill.tts_lora),
    )
```

**Total activation time: <5ms** (all three load concurrently, each takes 1-3ms
for a cached adapter).

## Why This Works: All Three Models Are Transformers

This isn't theoretical — it works because of a lucky architectural convergence:

- **Whisper** (STT): Encoder-decoder transformer → LoRA-compatible
- **Atlas Core / Qwen** (LLM): Decoder-only transformer → LoRA-compatible  
- **Orpheus** (TTS): Decoder-only transformer (generates audio tokens) → LoRA-compatible

All three use the same attention mechanism. All three support the same LoRA injection
points (q_proj, v_proj, k_proj, o_proj). The adapter format is identical — just
different shapes for different model dimensions.

## The Skill Package Manifest

```yaml
# skills/medical.yaml
name: medical
version: 1.2.0
description: Medical knowledge — drugs, anatomy, symptoms, treatment

adapters:
  stt:
    model: whisper-medium
    path: adapters/medical/stt.safetensors
    size_mb: 32
    rank: 8
    targets: [q_proj, v_proj]
    
  llm:
    model: atlas-core-1b
    path: adapters/medical/llm.safetensors
    size_mb: 80
    rank: 16
    targets: [q_proj, v_proj, k_proj, gate_proj]
    
  tts:
    model: orpheus-3b
    path: adapters/medical/tts.safetensors
    size_mb: 28
    rank: 8
    targets: [q_proj, v_proj]

triggers:
  keywords: [medication, symptom, diagnosis, treatment, drug, dose, ...]
  embedding_centroid: medical_centroid.npy
  confidence_threshold: 0.75

training:
  source: medical_conversations_10k.jsonl
  method: qlora
  epochs: 3
  last_trained: 2026-03-10
```

## Training a Complete Skill Package

### Phase 1: Generate Training Data

Start from the LLM — it's the easiest to get training data for:

```
1. Curate 5-10K domain-specific Q&A pairs
   (medical textbooks, pharmacology references, clinical guidelines)
   
2. Run through teacher model (Qwen3.5-35B or Claude) to generate
   high-quality responses with reasoning chains
   
3. This becomes the LLM training set
```

### Phase 2: Synthetic Audio Data Pipeline

Use the LLM training data to generate audio training data:

```
LLM training text ──→ TTS generates audio ──→ STT training pairs
      │                    │                         │
      │                    ├─ Correct pronunciation   │
      │                    └─ Multiple voices/speeds  │
      │                                              │
      └──────── Original text serves as ─────────────┘
                ground truth transcription
```

This creates a **self-reinforcing cycle**:
- Better TTS pronunciation → better synthetic audio
- Better synthetic audio → better STT training data
- Better STT → better transcriptions → better LLM input
- Repeat

### Phase 3: Train All Three (Sequential, One GPU)

```
Night 1: Train LLM LoRA on medical Q&A     (2-4 hours, RTX 4060)
Night 2: Train TTS LoRA on pronunciation    (4-6 hours, RTX 4060)
Night 3: Train STT LoRA on recognition      (2-4 hours, RTX 4060)
Night 4: Integration testing + benchmarks   (automated)
```

Total: 4 nights of off-hours training. ~$2 in electricity.

### Phase 4: Validate the Package

The skill package must pass three tests:
1. **STT accuracy**: Medical term WER < 5% (vs ~25% baseline)
2. **LLM quality**: Medical Q&A accuracy > 90% on domain benchmark
3. **TTS pronunciation**: Human evaluation score > 4.5/5 on drug names
4. **Integration**: End-to-end test — speak a medical question, verify entire
   pipeline handles it correctly

## What Skill Packages Would Atlas Need?

| Skill | STT Challenge | LLM Challenge | TTS Challenge |
|---|---|---|---|
| **Medical** | Drug names, anatomy | Interactions, dosing | Pronunciation |
| **Cooking** | Ingredients, techniques | Substitutions, timing | Foreign food names |
| **Home** | Smart device names | Automation logic | Room/device names |
| **Coding** | Programming terms | Code generation | Variable/function names |
| **Kids** | Child speech patterns | Age-appropriate answers | Expressive speech |
| **Science** | Chemical compounds | Explanations, equations | Technical terms |
| **Legal** | Legal terminology | Case references | Latin terms |
| **Music** | Song/artist names | Music theory, history | Composer names |

Each package is ~100-200MB. All 8 packages together: ~1.2GB. That's less than a
single 7B expert model.

## The Novel Part: Nobody Does This

As of 2025-2026:
- **LLM LoRA**: Extremely well-studied. Thousands of adapters on HuggingFace.
- **TTS LoRA**: Emerging. A few research papers, no production implementations.
- **STT LoRA**: Barely explored. Whisper fine-tuning exists but not as LoRA adapters.
- **Coordinated packages**: **Zero prior art.**

The insight isn't any single adapter — it's the coordination. Activating all three
simultaneously, training them from a shared dataset, and packaging them as a
deployable unit.

This is analogous to how the human brain works: when you enter "medical mode" (at
the doctor's office), your speech recognition, knowledge retrieval, AND speech
production all shift together. You don't independently activate "medical hearing"
then "medical thinking" then "medical speaking" — it's one holistic shift.

## References

- [LoRA: Low-Rank Adaptation](https://arxiv.org/abs/2106.09685) — Original paper
- [QLoRA](https://arxiv.org/abs/2305.14314) — Quantized LoRA for consumer hardware
- [Whisper LoRA Fine-Tuning](https://colab.research.google.com/github/Vaibhavs10/fast-whisper-finetuning/blob/main/Whisper_w_PEFT.ipynb)
- [UtterTune: TTS Fine-Tuning](https://github.com/shuheikatoinfo/UtterTune)
- [Parameter-Efficient TTS (Interspeech 2025)](https://www.isca-archive.org/interspeech_2025/kwon25_interspeech.pdf)
- [UAL: Universal Adopter LoRA](https://arxiv.org/abs/2502.15129)
