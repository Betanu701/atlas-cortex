# Qwen3-TTS vs Orpheus: Choosing a TTS Engine for Constrained GPU

## Research Date: 2026-03-14

## Summary

Deep comparative analysis of Qwen3-TTS and Orpheus TTS for a personal AI assistant
running on consumer GPUs (8-20GB VRAM). Key finding: **the runtime overhead gap**
(PyTorch vs llama.cpp) is the decisive factor on shared GPUs, not raw model quality.

## Key Findings

### Architecture Gap
- **Orpheus**: Pure Llama decoder → GGUF → llama.cpp native. Shares process with LLM.
- **Qwen3-TTS**: Custom Thinker-Talker + MTP → PyTorch/vLLM. Separate runtime.
- On a shared 8GB GPU, Orpheus uses ~0.7GB effective; Qwen3-TTS uses ~3.0GB effective.

### Qwen3-TTS Model Family
| Variant | Params | Disk | VRAM (with PyTorch) | Quality |
|---------|--------|------|:---:|---------|
| Qwen3-TTS-1.7B | 1.7B | 4.5GB | ~6.5GB | Excellent |
| Qwen3-TTS-0.6B | 600M | 2.5GB | ~4.0GB | Very good |
| 0.6B Pruned+Q4 | ~300M | 808MB | ~2.5GB | Good |

### Qwen3-TTS Unique Capabilities (Orpheus lacks these)
1. **Voice cloning** from 3-second audio sample
2. **Natural language emotion** ("speak angrily with a hint of sadness")
3. **Multilingual** (10+ languages natively)
4. **Streaming first-packet** latency: 97ms (vs ~200-300ms Orpheus)
5. **Free-form voice design** via text description

### Orpheus Unique Advantages
1. **Same runtime as LLM** (both in llama.cpp = zero extra overhead)
2. **3-4x smaller effective GPU footprint** on shared GPU
3. **Deterministic inline emotion tags** (better for scripted output)
4. **LoRA identical to LLM** (unified adapter tooling)
5. **GGUF native** (works with llama.cpp, Ollama, etc.)

### Compression Already Demonstrated
Community (AtomGradient) compressed Qwen3-TTS 0.6B from 2.35GB to 808MB:
- Vocabulary pruning (remove non-English tokens)
- MLP neuron pruning (30%)
- Transformer layer pruning (20%)
- 4-bit quantization
- Result: RTF 0.8, STOI >= 0.96, 97ms first-packet on Apple Silicon

### Emotion Control Comparison
| Feature | Qwen3-TTS | Orpheus |
|---------|-----------|---------|
| Control method | NL instructions + tags | Inline markup tags |
| Inline tag support | WIP/evolving | Robust, production |
| Emotion blending | Multi-intensity + blend | Fixed set |
| Determinism | Improving | High |
| Hallucination risk | Possible (laughter/sighing) | Low |

## Recommendation for Atlas

**Multi-GPU (dedicated TTS GPU)**: Qwen3-TTS 1.7B on NVIDIA GPU
- Voice cloning + NL emotions + full quality
- PyTorch runtime overhead doesn't matter with dedicated GPU

**Single GPU 12GB+**: Qwen3-TTS 0.6B compressed
- Fits alongside Core 2B with ~6.6GB headroom on 12GB

**Single GPU 8-12GB**: Orpheus-EN-1B Q4
- Shared llama.cpp process with Core 2B
- 4.7GB headroom on 8GB GPU

**CPU only / RPi**: Kokoro or Piper
- No GPU needed at all

## Sources
- Qwen3-TTS Technical Report: https://arxiv.org/pdf/2601.15621
- Qwen3-TTS GitHub: https://github.com/QwenLM/Qwen3-TTS
- AtomGradient compression: https://atomgradient.github.io/swift-qwen3-tts/
- Qwen3-TTS-0.6B-CustomVoice-4bit-pruned-vocab-lite: https://huggingface.co/AtomGradient/Qwen3-TTS-0.6B-CustomVoice-4bit-pruned-vocab-lite
- EmergentTTS-Eval: https://arxiv.org/html/2505.23009v1
- TTS Arena leaderboard: https://tts.ai/tts-arena/
- Orpheus (Canopy Labs): documented in atlas-cortex/docs/distillation-architecture.md
