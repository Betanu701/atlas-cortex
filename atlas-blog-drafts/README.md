# Atlas Blog Drafts

Draft articles from Atlas Cortex research sessions. Each article is self-contained
with full context, research findings, references, and enough detail to construct
a published blog post.

## Articles

| # | Title | Status | Key Insight |
|---|-------|--------|-------------|
| 01 | [Application-Aware MoE Surgery](articles/01-moe-surgery/article.md) | Draft | Profile your app's actual usage, then surgically remove the MoE experts it never activates |
| 02 | [GPU Choreography for Self-Evolving AI](articles/02-gpu-choreography/article.md) | Draft | Treat GPU VRAM like an OS treats RAM — dynamic allocation with priority preemption |
| 03 | [Two-Phase Self-Evolution on 8GB](articles/03-two-phase-selfmod/article.md) | Draft | Split AI self-modification into "thinker plans" + "typist executes" connected by a model swap |
| 04 | [Universal Distillation Philosophy](articles/04-universal-distillation/article.md) | Draft | Apply the same prune→distill→strip→quantize pipeline to every model in the stack |
| 05 | [Model Scout: Autonomous Model Evolution](articles/05-model-scout/article.md) | Draft | Let your AI discover, evaluate, and promote its own brain upgrades — with safety rails |
| 06 | [The Atlas Body: Bio-Inspired AI Architecture](articles/06-atlas-body/article.md) | Draft | Map every human body system to an AI component — discover 5 missing layers and a 40-60% latency reduction |
| 07 | [Breaking the I/O Wall: Zero-I/O Pipeline](articles/07-zero-io-pipeline/article.md) | Draft | Eliminate ~135ms HTTP overhead by running LLM, embeddings, and TTS in-process — making the pipeline compute-bound |
| 08 | [Universal Skill Packages](articles/08-universal-skill-packages/article.md) | Draft | Coordinate LoRA adapters across STT + LLM + TTS simultaneously — zero prior art in production |
| 09 | [Autonomous LoRA Training on Consumer Hardware](articles/09-autonomous-lora-training/article.md) | Draft | Train LoRA adapters overnight on a single RTX 4060 for $0.09/night — continuous autonomous improvement |
| 10 | [Composable LoRA Intelligence](articles/10-composable-lora-intelligence/article.md) | Draft | A 9B model with 13 dynamically fused domain LoRAs + memory + tools + live research outperforms 200B models on cross-domain synthesis |

## Source

Research conducted March 2026 as part of [Atlas Cortex](https://github.com/Betanu701/atlas-cortex).
Full research document: `atlas-cortex/docs/llm-optimization-strategy.md`

## How to Use

Each article directory contains:
- `article.md` — The full draft with background, technical details, diagrams, and references
- Future: images, code snippets, benchmark data as needed

Pick an article, flesh it out with your voice and any new benchmarks, and publish.
