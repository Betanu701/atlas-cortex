"""Voice Activity Detection using webrtcvad.

Lightweight C-based VAD — adds ~1MB memory. Supports 8/16/32/48kHz
with 10/20/30ms frames.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import webrtcvad
except ImportError:
    webrtcvad = None  # type: ignore[assignment]
    logger.warning("webrtcvad not installed — VAD disabled")


class VoiceActivityDetector:
    """Detects speech boundaries in audio frames."""

    def __init__(
        self,
        aggressiveness: int = 2,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        speech_threshold: int = 3,
        silence_threshold: int = 30,
        max_speech_frames: int = 500,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = int(sample_rate * frame_ms / 1000) * 2  # 16-bit
        self.speech_threshold = speech_threshold
        self.silence_threshold = silence_threshold
        # Max recording ~15s at 30ms/frame = 500 frames
        self.max_speech_frames = max_speech_frames

        self._vad = None
        if webrtcvad is not None:
            self._vad = webrtcvad.Vad(aggressiveness)

        self._speech_count = 0
        self._silence_count = 0
        self._in_speech = False
        self._speech_frame_total = 0

    def is_speech(self, audio_data: bytes) -> bool:
        """Check if a single frame contains speech."""
        if self._vad is None:
            return False
        try:
            return self._vad.is_speech(audio_data, self.sample_rate)
        except Exception:
            return False

    def process(self, audio_data: bytes) -> str:
        """Process a frame and return state: 'speech_start', 'speech', 'speech_end', 'silence'.

        State machine:
          silence → speech_start (after speech_threshold consecutive speech frames)
          speech → speech_end (after silence_threshold consecutive silence frames)
          speech → speech_end (after max_speech_frames total speech frames)
        """
        if self.is_speech(audio_data):
            self._speech_count += 1
            self._silence_count = 0

            if not self._in_speech and self._speech_count >= self.speech_threshold:
                self._in_speech = True
                self._speech_frame_total = self._speech_count
                return "speech_start"
            elif self._in_speech:
                self._speech_frame_total += 1
                # Force end if recording too long
                if self._speech_frame_total >= self.max_speech_frames:
                    logger.warning("Max speech duration reached (%d frames), forcing end",
                                   self._speech_frame_total)
                    self._in_speech = False
                    self._speech_frame_total = 0
                    return "speech_end"
                return "speech"
        else:
            self._silence_count += 1
            self._speech_count = 0

            if self._in_speech and self._silence_count >= self.silence_threshold:
                self._in_speech = False
                self._speech_frame_total = 0
                return "speech_end"

        return "silence"

    def reset(self) -> None:
        """Reset speech/silence counters."""
        self._speech_count = 0
        self._silence_count = 0
        self._in_speech = False
        self._speech_frame_total = 0

    @property
    def active(self) -> bool:
        return self._vad is not None
