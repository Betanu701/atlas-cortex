# Orpheus LoRA Vocabulary Research — Agent Instructions

## Context

This research explores using LoRA adapters to improve TTS (Orpheus) pronunciation
and STT (Whisper) recognition of specialized vocabulary — medication names, medical
terms, and other domain-specific language.

**Primary research doc:** `research/orpheus-lora-vocabulary/research.md`
**Related article:** `articles/08-universal-skill-packages/article.md`

## When Continuing This Research

1. **Read `research/orpheus-lora-vocabulary/research.md` first** — it has the full
   context, open questions, code examples, and references.

2. **Key open questions to pursue:**
   - Can Orpheus emotion tags survive LoRA fine-tuning?
   - Practical synthetic data pipeline: LLM → TTS → STT training pairs
   - Adapter interference when combining multiple domain LoRAs
   - Whisper v3 LoRA fine-tuning without losing multilingual capability
   - Incremental adapter updates vs full retraining

3. **Hardware for experiments:**
   - RTX 4060 (8GB) — fits QLoRA training on Orpheus 3B and Whisper medium
   - Training time: 4-6 hours for TTS LoRA, 2-4 hours for STT LoRA

4. **Tools to use:**
   - HuggingFace PEFT for LoRA application
   - Unsloth for faster QLoRA training
   - bitsandbytes for 4-bit quantization during training

5. **Save any novel findings as blog articles** in this repo following the existing
   pattern: `articles/NN-short-slug/article.md`

## This Is Separate From

- The main LLM optimization strategy (atlas-cortex `docs/llm-optimization-strategy.md`)
- The bio-architecture plan (atlas-cortex `docs/bio-architecture-plan.md`)
- Those are in the atlas-cortex repo. This research thread is private to this repo.
