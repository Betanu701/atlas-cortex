"""Atlas Cortex — standalone OpenAI-compatible server (port 5100).

Implements:
  POST /v1/audio/speech   — TTS endpoint (C11.6)
  GET  /v1/audio/voices   — list available voices
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cortex.voice.providers import get_tts_provider
from cortex.voice.composer import EmotionComposer

app = FastAPI(title="Atlas Cortex", version="1.0.0")

_composer = EmotionComposer()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SpeechRequest(BaseModel):
    """OpenAI-compatible speech synthesis request with Atlas extensions."""

    input: str = Field(..., description="Text to synthesize")
    voice: str = Field("tara", description="Voice ID (e.g. 'tara', 'orpheus_leo')")
    model: str = Field("orpheus", description="TTS provider/model name")
    response_format: str = Field("wav", description="Audio format: wav | mp3 | ogg")
    speed: float = Field(1.0, ge=0.25, le=4.0, description="Speech speed multiplier")

    # Atlas extensions
    emotion: str | None = Field(None, description="Explicit emotion override (e.g. 'warm', 'sad')")
    include_phonemes: bool = Field(False, description="Include phoneme timing in X-Phonemes header")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/audio/speech")
async def create_speech(req: SpeechRequest):
    """Synthesise speech from text, returning a streaming audio response.

    Compatible with the OpenAI /v1/audio/speech API.
    Atlas extensions: ``emotion`` and ``include_phonemes``.
    """
    try:
        provider = get_tts_provider({"TTS_PROVIDER": req.model})
    except ValueError:
        # Unknown model/provider — fall back to configured default
        provider = get_tts_provider()

    # Apply emotion composer if no explicit emotion override
    text = req.input
    if not req.emotion:
        # Neutral sentiment object for plain API calls (no pipeline context)
        class _NeutralSentiment:
            label = "neutral"
            compound = 0.0
            category = "neutral"

        composed = _composer.compose(
            text,
            _NeutralSentiment(),
            provider=provider,
        )
        if isinstance(composed, tuple):
            text = composed[0]
        else:
            text = composed
    else:
        # Prepend caller-supplied emotion descriptor (Orpheus format)
        fmt = provider.get_emotion_format()
        if fmt == "tags" and req.emotion:
            text = f"{req.emotion}: {text}"

    media_type = _format_to_media_type(req.response_format)

    async def _audio_stream() -> AsyncGenerator[bytes, None]:
        async for chunk in provider.synthesize(
            text,
            voice=req.voice,
            emotion=req.emotion,
            speed=req.speed,
            stream=True,
        ):
            yield chunk

    return StreamingResponse(
        _audio_stream(),
        media_type=media_type,
        headers={"X-Voice": req.voice, "X-Provider": req.model},
    )


@app.get("/v1/audio/voices")
async def list_voices_endpoint():
    """List available TTS voices for the configured provider."""
    provider = get_tts_provider()
    voices = await provider.list_voices()
    return {"voices": voices}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_to_media_type(fmt: str) -> str:
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "pcm": "audio/pcm",
    }.get(fmt.lower(), "audio/wav")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("CORTEX_HOST", "0.0.0.0")
    port = int(os.environ.get("CORTEX_PORT", "5100"))
    uvicorn.run("cortex.server:app", host=host, port=port, reload=False)
