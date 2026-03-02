"""WebSocket endpoint for satellite audio streaming and control.

Handles the real-time communication channel between Atlas server and
satellite devices:

  Satellite → Server:
    ANNOUNCE, WAKE, AUDIO_START, AUDIO_CHUNK, AUDIO_END, STATUS, HEARTBEAT

  Server → Satellite:
    ACCEPTED, TTS_START, TTS_CHUNK, TTS_END, PLAY_FILLER,
    COMMAND, CONFIG, SYNC_FILLERS
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import struct
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from cortex.db import get_db, init_db

logger = logging.getLogger(__name__)

# STT configuration — supports "whisper_cpp" (HTTP) and "wyoming" (TCP) backends
_STT_BACKEND = os.environ.get("STT_BACKEND", "whisper_cpp")
_STT_HOST = os.environ.get("STT_HOST", "localhost")
_STT_PORT = int(os.environ.get("STT_PORT", "10300"))
_PIPER_HOST = os.environ.get("PIPER_HOST", os.environ.get("TTS_HOST", "localhost"))
_PIPER_PORT = int(os.environ.get("PIPER_PORT", os.environ.get("TTS_PORT", "10200")))


def _get_satellite_voice(satellite_id: str) -> str:
    """Read the configured TTS voice for a satellite from DB."""
    try:
        db = get_db()
        row = db.execute(
            "SELECT tts_voice FROM satellites WHERE id = ?", (satellite_id,)
        ).fetchone()
        return (row["tts_voice"] or "") if row else ""
    except Exception:
        return ""


def _get_orpheus_provider():
    """Return the Orpheus TTS provider if configured, else None."""
    try:
        from cortex.voice.providers import get_tts_provider, _env_config
        cfg = _env_config()
        if cfg.get("TTS_PROVIDER", "orpheus").lower() == "orpheus":
            return get_tts_provider(cfg)
    except Exception:
        pass
    return None


# ── Connection registry ───────────────────────────────────────────

_connected_satellites: dict[str, SatelliteConnection] = {}


class SatelliteConnection:
    """Tracks a connected satellite's WebSocket and metadata."""

    def __init__(self, websocket: WebSocket, satellite_id: str) -> None:
        self.websocket = websocket
        self.satellite_id = satellite_id
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.session_id: str | None = None
        self.audio_buffer: bytearray = bytearray()
        self.audio_format: dict = {}

    async def send(self, message: dict) -> None:
        """Send a JSON message to the satellite."""
        await self.websocket.send_json(message)

    async def send_command(self, action: str, params: dict | None = None) -> None:
        """Send a COMMAND message."""
        await self.send({
            "type": "COMMAND",
            "action": action,
            "params": params or {},
        })


def get_connected_satellites() -> dict[str, SatelliteConnection]:
    """Return all currently connected satellite connections."""
    return _connected_satellites.copy()


def get_connection(satellite_id: str) -> SatelliteConnection | None:
    """Get a specific satellite's connection."""
    return _connected_satellites.get(satellite_id)


# ── WebSocket handler ─────────────────────────────────────────────


async def satellite_ws_handler(websocket: WebSocket) -> None:
    """Handle a satellite WebSocket connection.

    This is the main entry point — mount it in FastAPI via:
        app.add_api_websocket_route("/ws/satellite", satellite_ws_handler)
    """
    await websocket.accept()
    satellite_id: str | None = None
    conn = SatelliteConnection(websocket, "")

    try:
        # First message must be ANNOUNCE
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        if raw.get("type") != "ANNOUNCE":
            await websocket.send_json({"type": "ERROR", "detail": "Expected ANNOUNCE"})
            await websocket.close()
            return

        satellite_id = raw.get("satellite_id", "")
        if not satellite_id:
            await websocket.send_json({"type": "ERROR", "detail": "Missing satellite_id"})
            await websocket.close()
            return

        conn.satellite_id = satellite_id
        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        conn.session_id = session_id

        # Register connection
        _connected_satellites[satellite_id] = conn

        # Extract client IP and metadata from ANNOUNCE
        client_ip = websocket.client.host if websocket.client else None
        _update_satellite_status(
            satellite_id, "online",
            ip_address=client_ip,
            hostname=raw.get("hostname"),
            room=raw.get("room"),
            capabilities=raw.get("capabilities"),
            hardware_info=raw.get("hw_info"),
        )

        # Send ACCEPTED
        await conn.send({
            "type": "ACCEPTED",
            "satellite_id": satellite_id,
            "session_id": session_id,
        })

        logger.info("Satellite connected: %s (session %s)", satellite_id, session_id)

        # Message loop
        async for raw_msg in websocket.iter_json():
            msg_type = raw_msg.get("type", "")

            if msg_type == "HEARTBEAT":
                await _handle_heartbeat(conn, raw_msg)

            elif msg_type == "WAKE":
                await _handle_wake(conn, raw_msg)

            elif msg_type == "AUDIO_START":
                await _handle_audio_start(conn, raw_msg)

            elif msg_type == "AUDIO_CHUNK":
                await _handle_audio_chunk(conn, raw_msg)

            elif msg_type == "AUDIO_END":
                await _handle_audio_end(conn, raw_msg)

            elif msg_type == "STATUS":
                await _handle_status(conn, raw_msg)

            else:
                logger.warning(
                    "Unknown message type from %s: %s", satellite_id, msg_type
                )

    except WebSocketDisconnect:
        logger.info("Satellite disconnected: %s", satellite_id)
    except asyncio.TimeoutError:
        logger.warning("Satellite connection timed out (no ANNOUNCE)")
    except Exception:
        logger.exception("Error in satellite WebSocket for %s", satellite_id)
    finally:
        if satellite_id:
            _connected_satellites.pop(satellite_id, None)
            _update_satellite_status(satellite_id, "offline")


# ── Message handlers ──────────────────────────────────────────────


async def _handle_heartbeat(conn: SatelliteConnection, msg: dict) -> None:
    """Update satellite status from heartbeat."""
    conn.last_heartbeat = time.time()
    try:
        db = get_db()
        db.execute(
            """UPDATE satellites
               SET last_seen = ?, uptime_seconds = ?, wifi_rssi = ?, cpu_temp = ?
               WHERE id = ?""",
            (
                datetime.now(timezone.utc).isoformat(),
                msg.get("uptime"),
                msg.get("wifi_rssi"),
                msg.get("cpu_temp"),
                conn.satellite_id,
            ),
        )
        db.commit()
    except Exception:
        logger.exception("Failed to update heartbeat for %s", conn.satellite_id)


async def _handle_wake(conn: SatelliteConnection, msg: dict) -> None:
    """Handle wake word detection from satellite."""
    logger.info(
        "Wake word from %s (confidence: %.2f)",
        conn.satellite_id,
        msg.get("wake_word_confidence", 0),
    )
    # Create an audio session
    session_id = f"audio-{uuid.uuid4().hex[:8]}"
    conn.session_id = session_id
    try:
        db = get_db()
        db.execute(
            "INSERT INTO satellite_audio_sessions (id, satellite_id) VALUES (?, ?)",
            (session_id, conn.satellite_id),
        )
        db.commit()
    except Exception:
        logger.exception("Failed to create audio session")


async def _handle_audio_start(conn: SatelliteConnection, msg: dict) -> None:
    """Audio streaming has started from the satellite."""
    conn.audio_buffer = bytearray()
    conn.audio_format = msg.get("format_info", {"rate": 16000, "width": 2, "channels": 1})
    logger.debug("Audio start from %s (format: %s)", conn.satellite_id, msg.get("format"))


async def _handle_audio_chunk(conn: SatelliteConnection, msg: dict) -> None:
    """Receive an audio chunk from the satellite and buffer it."""
    audio_b64 = msg.get("audio", "")
    if audio_b64:
        conn.audio_buffer.extend(base64.b64decode(audio_b64))


async def _handle_audio_end(conn: SatelliteConnection, msg: dict) -> None:
    """Audio streaming has ended — run STT → Pipeline → TTS."""
    reason = msg.get("reason", "vad_silence")
    audio_data = bytes(conn.audio_buffer)
    conn.audio_buffer = bytearray()

    logger.info(
        "Audio end from %s (reason: %s, %d bytes)",
        conn.satellite_id, reason, len(audio_data),
    )

    # Update session
    if conn.session_id:
        try:
            db = get_db()
            db.execute(
                "UPDATE satellite_audio_sessions SET ended_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), conn.session_id),
            )
            db.commit()
        except Exception:
            pass

    if len(audio_data) < 1600:
        # Too short to be meaningful speech (~50ms)
        logger.debug("Audio too short (%d bytes), ignoring", len(audio_data))
        return

    # Cap audio at ~15 seconds (480000 bytes at 16kHz 16-bit mono) to prevent
    # VAD runaway and whisper hallucination on very long recordings.
    MAX_AUDIO_BYTES = 480000  # 15 seconds
    if len(audio_data) > MAX_AUDIO_BYTES:
        logger.warning(
            "Audio from %s too long (%d bytes / %.1fs), truncating to last %.0fs",
            conn.satellite_id, len(audio_data),
            len(audio_data) / 32000, MAX_AUDIO_BYTES / 32000,
        )
        audio_data = audio_data[-MAX_AUDIO_BYTES:]

    # Run the voice pipeline in a background task so websocket stays responsive
    asyncio.create_task(_process_voice_pipeline(conn, audio_data))


async def _handle_status(conn: SatelliteConnection, msg: dict) -> None:
    """Update satellite status (idle, listening, speaking)."""
    status = msg.get("status", "idle")
    logger.debug("Satellite %s status: %s", conn.satellite_id, status)


# ── Voice pipeline ────────────────────────────────────────────────


def _is_hallucinated(transcript: str) -> bool:
    """Detect whisper hallucination patterns (repeated phrases, noise)."""
    words = transcript.split()
    if len(words) < 3:
        return False
    # Check for repeated short phrases (e.g. "Okay. Okay. Okay.")
    segments = [s.strip() for s in transcript.replace("\n", " ").split(".") if s.strip()]
    if len(segments) >= 4:
        unique = set(s.lower() for s in segments)
        if len(unique) <= 2:
            return True
    # Common whisper hallucinations on silence
    lower = transcript.lower().strip()
    hallucination_patterns = [
        "thank you for watching",
        "thanks for watching",
        "please subscribe",
        "you",
        "...",
    ]
    if lower in hallucination_patterns:
        return True
    return False


_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at punctuation boundaries.

    Keeps short fragments together to avoid tiny TTS calls.
    Minimum sentence length ~20 chars before splitting.
    """
    raw = _SENTENCE_RE.split(text.strip())
    if not raw:
        return [text.strip()] if text.strip() else []

    sentences: list[str] = []
    buf = ""
    for part in raw:
        buf = (buf + " " + part).strip() if buf else part
        if len(buf) >= 20:
            sentences.append(buf)
            buf = ""
    if buf:
        if sentences:
            sentences[-1] = sentences[-1] + " " + buf
        else:
            sentences.append(buf)
    return sentences


async def _process_voice_pipeline(conn: SatelliteConnection, audio_data: bytes) -> None:
    """Full STT → Pipeline → TTS → stream back to satellite."""

    satellite_id = conn.satellite_id
    t_start = time.monotonic()

    # Always import Wyoming for Piper TTS (filler + fallback)
    from cortex.voice.wyoming import WyomingClient, WyomingError

    try:
        # ── Step 1: STT ──────────────────────────────────────────
        t_stt_start = time.monotonic()
        logger.info("Running STT on %d bytes (%.1fs audio) from %s (backend=%s)",
                     len(audio_data), len(audio_data) / 32000,
                     satellite_id, _STT_BACKEND)

        try:
            if _STT_BACKEND == "whisper_cpp":
                from cortex.voice.whisper_cpp import WhisperCppClient, WhisperCppError
                stt_client = WhisperCppClient(_STT_HOST, _STT_PORT, timeout=60.0)
                transcript = await stt_client.transcribe(audio_data, sample_rate=16000)
            else:
                from cortex.voice.wyoming import WyomingClient, WyomingError as _WErr
                stt_client = WyomingClient(_STT_HOST, _STT_PORT, timeout=30.0)
                transcript = await stt_client.transcribe(audio_data, sample_rate=16000)
        except Exception as e:
            logger.error("STT failed for %s: %s", satellite_id, e)
            try:
                await conn.send({"type": "PIPELINE_ERROR", "detail": f"STT failed: {e}"})
            except Exception:
                pass
            return

        transcript = transcript.strip()
        t_stt_end = time.monotonic()
        stt_ms = (t_stt_end - t_stt_start) * 1000

        if not transcript:
            logger.info("Empty transcript from %s (STT took %.0fms), ignoring", satellite_id, stt_ms)
            try:
                await conn.send({"type": "PIPELINE_ERROR", "detail": "Empty transcript"})
            except Exception:
                pass
            return

        # Guard against whisper hallucination (repeated noise patterns)
        if _is_hallucinated(transcript):
            logger.warning("Hallucinated transcript from %s (%.0fms): %r — dropping",
                           satellite_id, stt_ms, transcript[:100])
            try:
                await conn.send({"type": "PIPELINE_ERROR", "detail": "No clear speech detected"})
            except Exception:
                pass
            return

        logger.info("STT result from %s (%.0fms): %r", satellite_id, stt_ms, transcript)

        # ── Step 2: Pipeline (filler-first streaming) ─────────────
        t_llm_start = time.monotonic()
        from cortex.providers import get_provider
        from cortex.pipeline import run_pipeline

        provider = get_provider()

        pipeline_gen = await run_pipeline(
            message=transcript,
            provider=provider,
            satellite_id=satellite_id,
            model_fast="qwen2.5:7b",
        )

        # Layer 3 yields filler text first, then LLM tokens.
        # Synthesize and stream the filler immediately via Piper (fast, <300ms)
        # while continuing to collect LLM tokens.
        filler_text = ""
        response_parts: list[str] = []
        first_token = True
        tts_voice = _get_satellite_voice(satellite_id)

        async for token in pipeline_gen:
            if first_token:
                first_token = False
                filler_text = token.strip()
                if filler_text:
                    # Synthesize filler via Piper (CPU, ~200ms) and stream immediately
                    t_filler_start = time.monotonic()
                    try:
                        piper = WyomingClient(_PIPER_HOST, _PIPER_PORT, timeout=10.0)
                        piper_voice = tts_voice if tts_voice and not tts_voice.startswith("orpheus_") else None
                        filler_audio, filler_info = await piper.synthesize(filler_text, voice=piper_voice)
                        filler_rate = filler_info.get("rate", 22050)
                        filler_ms = (time.monotonic() - t_filler_start) * 1000

                        logger.info("Filler TTS for %s: %r (%.0fms, %d bytes)",
                                    satellite_id, filler_text, filler_ms, len(filler_audio))

                        # Stream filler to satellite immediately
                        await conn.send({
                            "type": "TTS_START",
                            "session_id": conn.session_id,
                            "format": f"pcm_{filler_rate // 1000}k_16bit_mono",
                            "sample_rate": filler_rate,
                            "text": filler_text,
                            "is_filler": True,
                        })
                        chunk_size = 4096
                        for offset in range(0, len(filler_audio), chunk_size):
                            chunk = filler_audio[offset:offset + chunk_size]
                            await conn.send({
                                "type": "TTS_CHUNK",
                                "session_id": conn.session_id,
                                "audio": base64.b64encode(chunk).decode("ascii"),
                            })
                        await conn.send({
                            "type": "TTS_END",
                            "session_id": conn.session_id,
                            "is_filler": True,
                        })
                    except Exception as e:
                        logger.warning("Filler TTS failed: %s", e)
                continue
            response_parts.append(token)

        full_response = "".join(response_parts).strip()
        t_llm_end = time.monotonic()
        llm_ms = (t_llm_end - t_llm_start) * 1000

        if not full_response:
            logger.warning("Empty pipeline response for %r (LLM took %.0fms)", transcript, llm_ms)
            return

        logger.info("Pipeline response for %s (LLM %.0fms): %r", satellite_id, llm_ms, full_response[:200])

        # ── Step 3: TTS ──────────────────────────────────────────
        # Piper primary: CPU, very fast (~200ms for typical response)
        # Orpheus fallback: GPU, higher quality but ~1s/word currently
        t_tts_start = time.monotonic()
        tts_used = "none"
        total_tts_bytes = 0
        tts_audio = b""
        tts_rate = 22050

        # Use Piper for fast TTS (always available, CPU)
        try:
            piper = WyomingClient(_PIPER_HOST, _PIPER_PORT, timeout=30.0)
            piper_voice = tts_voice if tts_voice and not tts_voice.startswith("orpheus_") else None
            tts_audio, audio_info = await piper.synthesize(full_response, voice=piper_voice)
            tts_rate = audio_info.get("rate", 22050)
            tts_used = "piper"
        except WyomingError as e:
            logger.warning("Piper TTS failed: %s", e)

        # Orpheus fallback (GPU, higher quality voice, slower)
        if not tts_audio:
            orpheus = _get_orpheus_provider()
            if orpheus:
                try:
                    orpheus_voices = {"tara", "leah", "jess", "leo", "dan", "mia", "zac", "zoe"}
                    orpheus_voice = tts_voice if tts_voice.replace("orpheus_", "") in orpheus_voices else "tara"
                    chunks = []
                    async for chunk in orpheus.synthesize(full_response, voice=orpheus_voice):
                        chunks.append(chunk)
                    tts_audio = b"".join(chunks)
                    if tts_audio:
                        if tts_audio[:4] == b"RIFF":
                            import wave, io
                            with wave.open(io.BytesIO(tts_audio), "rb") as wf:
                                tts_rate = wf.getframerate()
                                tts_audio = wf.readframes(wf.getnframes())
                        else:
                            tts_rate = 24000
                        tts_used = "orpheus"
                except Exception as e:
                    logger.error("Orpheus TTS also failed: %s", e)

        if not tts_audio:
            logger.warning("All TTS failed for %s", satellite_id)
            return

        t_tts_end = time.monotonic()
        tts_ms = (t_tts_end - t_tts_start) * 1000
        total_tts_bytes = len(tts_audio)

        logger.info("TTS [%s] %.0fms, %d bytes (%dHz) for %s",
                     tts_used, tts_ms, total_tts_bytes, tts_rate, satellite_id)

        # ── Step 4: Stream to satellite ──────────────────────────
        await conn.send({
            "type": "TTS_START",
            "session_id": conn.session_id,
            "format": f"pcm_{tts_rate // 1000}k_16bit_mono",
            "sample_rate": tts_rate,
            "text": full_response,
        })

        chunk_size = 4096
        for offset in range(0, len(tts_audio), chunk_size):
            chunk = tts_audio[offset:offset + chunk_size]
            await conn.send({
                "type": "TTS_CHUNK",
                "session_id": conn.session_id,
                "audio": base64.b64encode(chunk).decode("ascii"),
            })

        await conn.send({
            "type": "TTS_END",
            "session_id": conn.session_id,
        })

        t_total = time.monotonic() - t_start
        logger.info(
            "Pipeline complete for %s: total=%.1fs (STT=%.0fms LLM=%.0fms TTS=%.0fms [%s] %d bytes)",
            satellite_id, t_total, stt_ms, llm_ms, tts_ms, tts_used, total_tts_bytes,
        )

    except WebSocketDisconnect:
        logger.warning("Satellite %s disconnected during pipeline", satellite_id)
    except Exception:
        logger.exception("Voice pipeline error for %s", satellite_id)
        # Notify satellite to return to IDLE on failure
        try:
            await conn.send({"type": "PIPELINE_ERROR", "detail": "Voice pipeline failed"})
        except Exception:
            pass


def _resample_pcm(data: bytes, src_rate: int, dst_rate: int, channels: int = 1) -> bytes:
    """Simple linear interpolation resampling for 16-bit PCM."""
    if src_rate == dst_rate:
        return data
    samples_per_frame = channels
    n_frames = len(data) // (2 * samples_per_frame)
    if n_frames == 0:
        return data

    # Decode to samples (mono for simplicity)
    if channels > 1:
        # Mix to mono first
        all_samples = struct.unpack(f"<{n_frames * channels}h", data[:n_frames * channels * 2])
        mono = []
        for i in range(0, len(all_samples), channels):
            mono.append(sum(all_samples[i:i+channels]) // channels)
    else:
        mono = list(struct.unpack(f"<{n_frames}h", data[:n_frames * 2]))

    # Resample via linear interpolation
    ratio = src_rate / dst_rate
    new_len = int(n_frames / ratio)
    resampled = []
    for i in range(new_len):
        src_pos = i * ratio
        idx = int(src_pos)
        frac = src_pos - idx
        if idx + 1 < len(mono):
            val = int(mono[idx] * (1 - frac) + mono[idx + 1] * frac)
        else:
            val = mono[min(idx, len(mono) - 1)]
        resampled.append(max(-32768, min(32767, val)))

    return struct.pack(f"<{len(resampled)}h", *resampled)


# ── Helpers ───────────────────────────────────────────────────────


def _update_satellite_status(
    satellite_id: str,
    status: str,
    ip_address: str | None = None,
    hostname: str | None = None,
    room: str | None = None,
    capabilities: list | None = None,
    hardware_info: dict | None = None,
) -> None:
    """Update the satellite status in the database (upsert)."""
    try:
        import json as _json

        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        caps_json = _json.dumps(capabilities) if capabilities else None
        hw_json = _json.dumps(hardware_info) if hardware_info else None

        db.execute(
            """INSERT INTO satellites (id, display_name, status, last_seen,
                   ip_address, hostname, room, capabilities, hardware_info)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   status = ?,
                   last_seen = ?,
                   ip_address = COALESCE(?, ip_address),
                   hostname = COALESCE(?, hostname),
                   room = COALESCE(?, room),
                   capabilities = COALESCE(?, capabilities),
                   hardware_info = COALESCE(?, hardware_info)""",
            (
                satellite_id, satellite_id, status, now,
                ip_address, hostname, room, caps_json, hw_json,
                status, now,
                ip_address, hostname, room, caps_json, hw_json,
            ),
        )
        db.commit()
    except Exception:
        logger.exception("Failed to update satellite status: %s", satellite_id)


# ── Utility functions for sending to satellites ───────────────────


async def send_play_filler(satellite_id: str) -> bool:
    """Tell a satellite to play a cached filler phrase."""
    conn = _connected_satellites.get(satellite_id)
    if conn:
        await conn.send({"type": "PLAY_FILLER", "session_id": conn.session_id})
        return True
    return False


async def send_command(satellite_id: str, action: str, params: dict | None = None) -> bool:
    """Send a command to a connected satellite."""
    conn = _connected_satellites.get(satellite_id)
    if conn:
        await conn.send_command(action, params)
        return True
    return False


async def send_config(satellite_id: str, config: dict) -> bool:
    """Push configuration to a connected satellite."""
    conn = _connected_satellites.get(satellite_id)
    if conn:
        await conn.send({"type": "CONFIG", **config})
        return True
    return False
