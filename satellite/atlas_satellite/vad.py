"""Voice Activity Detection using webrtcvad with energy gating.

Lightweight C-based VAD — adds ~1MB memory. Supports 8/16/32/48kHz
with 10/20/30ms frames.

Uses energy-based pre-filtering and a sliding window for robust
silence detection on noisy microphones (e.g. ReSpeaker HAT).
"""

from __future__ import annotations

import collections
import logging
import struct

logger = logging.getLogger(__name__)

try:
    import webrtcvad
except ImportError:
    webrtcvad = None  # type: ignore[assignment]
    logger.warning("webrtcvad not installed — VAD disabled")


def _rms(audio_data: bytes) -> float:
    """Compute RMS energy of 16-bit PCM audio."""
    n = len(audio_data) // 2
    if n == 0:
        return 0.0
    samples = struct.unpack(f"<{n}h", audio_data[:n * 2])
    return (sum(s * s for s in samples) / n) ** 0.5


class VoiceActivityDetector:
    """Detects speech boundaries in audio frames.

    Improvements over pure webrtcvad consecutive-frame counting:
    1. Energy gate: frames below ``energy_threshold`` RMS are forced to
       silence regardless of webrtcvad's opinion.  Prevents mic noise
       from being classified as speech.
    2. Sliding window: instead of requiring N *consecutive* silence
       frames, we track the last ``window_size`` frames.  If the silence
       ratio in the window exceeds ``silence_ratio``, we trigger
       speech_end.  This handles intermittent noise spikes during pauses.
    """

    def __init__(
        self,
        aggressiveness: int = 1,
        sample_rate: int = 16000,
        frame_ms: int = 30,
        speech_threshold: int = 3,
        silence_threshold: int = 15,
        max_speech_frames: int = 333,
        energy_threshold: float = 80.0,
        window_size: int = 30,
        silence_ratio: float = 0.65,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = int(sample_rate * frame_ms / 1000) * 2  # 16-bit
        self.speech_threshold = speech_threshold
        self.silence_threshold = silence_threshold
        # Max recording ~10s at 30ms/frame = 333 frames
        self.max_speech_frames = max_speech_frames
        self.energy_threshold = energy_threshold
        self.window_size = window_size
        self.silence_ratio = silence_ratio

        self._vad = None
        if webrtcvad is not None:
            self._vad = webrtcvad.Vad(aggressiveness)

        self._speech_count = 0
        self._silence_count = 0
        self._in_speech = False
        self._speech_frame_total = 0
        # Sliding window: True = speech, False = silence
        self._window: collections.deque[bool] = collections.deque(maxlen=window_size)

    def is_speech(self, audio_data: bytes) -> bool:
        """Check if a single frame contains speech (with energy gate)."""
        if self._vad is None:
            return False
        # Energy gate: below threshold → silence, skip webrtcvad
        if _rms(audio_data) < self.energy_threshold:
            return False
        try:
            return self._vad.is_speech(audio_data, self.sample_rate)
        except Exception:
            return False

    def process(self, audio_data: bytes) -> str:
        """Process a frame and return state.

        Returns: 'speech_start', 'speech', 'speech_end', or 'silence'.

        State machine:
          silence → speech_start (after speech_threshold consecutive speech frames)
          speech → speech_end (sliding window: silence_ratio exceeded OR
                               consecutive silence_threshold frames)
          speech → speech_end (after max_speech_frames total speech frames)
        """
        frame_is_speech = self.is_speech(audio_data)
        self._window.append(frame_is_speech)

        if frame_is_speech:
            self._speech_count += 1
            self._silence_count = 0

            if not self._in_speech and self._speech_count >= self.speech_threshold:
                self._in_speech = True
                self._speech_frame_total = self._speech_count
                return "speech_start"
            elif self._in_speech:
                self._speech_frame_total += 1
                if self._speech_frame_total >= self.max_speech_frames:
                    logger.warning("Max speech duration reached (%d frames), forcing end",
                                   self._speech_frame_total)
                    self._reset_state()
                    return "speech_end"
                return "speech"
        else:
            self._silence_count += 1
            self._speech_count = 0

            if self._in_speech:
                # Method 1: consecutive silence (original)
                if self._silence_count >= self.silence_threshold:
                    self._reset_state()
                    return "speech_end"
                # Method 2: sliding window ratio
                if len(self._window) >= self.window_size:
                    n_silence = sum(1 for v in self._window if not v)
                    if n_silence / len(self._window) >= self.silence_ratio:
                        logger.info(
                            "Silence via window ratio (%.0f%% in %d frames)",
                            100 * n_silence / len(self._window),
                            len(self._window),
                        )
                        self._reset_state()
                        return "speech_end"

        return "silence"

    def _reset_state(self) -> None:
        self._in_speech = False
        self._speech_frame_total = 0
        self._speech_count = 0
        self._silence_count = 0

    def reset(self) -> None:
        """Reset speech/silence counters and window."""
        self._reset_state()
        self._window.clear()

    @property
    def active(self) -> bool:
        return self._vad is not None
