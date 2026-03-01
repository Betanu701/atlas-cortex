"""SNAC audio token decoder for Orpheus TTS.

Decodes Orpheus model output tokens (custom_token_NNNNN) into PCM audio.
Orpheus generates SNAC (Scalable Neural Audio Codec) tokens which must be
decoded through the hubertsiuzdak/snac_24khz model to produce audio.

Output: 24kHz 16-bit mono PCM audio.
"""

from __future__ import annotations

import logging
import re
import struct
from typing import Optional

logger = logging.getLogger(__name__)

# Regex to extract custom token IDs from Orpheus output
_TOKEN_RE = re.compile(r"<custom_token_(\d+)>")

# SNAC model singleton (lazy-loaded)
_snac_model = None
_snac_device = "cpu"
_torch_available = False

try:
    import torch
    import numpy as np
    _torch_available = True
except ImportError:
    logger.warning("PyTorch not available — SNAC decoding disabled (Orpheus TTS will not work via Ollama)")


def _load_snac_model():
    """Lazy-load the SNAC decoder model."""
    global _snac_model, _snac_device
    if _snac_model is not None:
        return _snac_model
    if not _torch_available:
        raise RuntimeError("PyTorch is required for SNAC decoding")

    from snac import SNAC
    logger.info("Loading SNAC decoder model (hubertsiuzdak/snac_24khz)...")
    _snac_model = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
    _snac_device = "cpu"  # Always CPU for cortex — GPU used by Ollama
    _snac_model = _snac_model.to(_snac_device)
    logger.info("SNAC decoder loaded on %s", _snac_device)
    return _snac_model


def extract_token_ids(text: str) -> list[int]:
    """Extract SNAC token IDs from Orpheus model output text.

    The model outputs ``<custom_token_NNNNN>`` strings.  Each token's raw ID
    must be offset-corrected: ``id = raw_id - 10 - (position_in_group % 7) * 4096``
    where position_in_group is the index within the 7-token frame.
    """
    raw_ids = [int(m) for m in _TOKEN_RE.findall(text)]
    corrected = []
    for i, raw_id in enumerate(raw_ids):
        layer = i % 7
        corrected_id = raw_id - 10 - layer * 4096
        corrected.append(corrected_id)
    return corrected


def decode_tokens(token_ids: list[int]) -> Optional[bytes]:
    """Decode a list of SNAC token IDs into raw PCM audio bytes (24kHz, 16-bit, mono).

    Returns None if decoding fails or input is too short.
    """
    if not _torch_available:
        logger.error("PyTorch not available for SNAC decoding")
        return None

    if len(token_ids) < 7:
        logger.warning("Too few tokens for SNAC decoding: %d (need >= 7)", len(token_ids))
        return None

    model = _load_snac_model()

    # Truncate to multiple of 7
    num_frames = len(token_ids) // 7
    token_ids = token_ids[:num_frames * 7]

    try:
        frame_tensor = torch.tensor(token_ids, dtype=torch.int32, device=_snac_device)
        frames = frame_tensor.reshape(num_frames, 7)

        # Build 3 codebook levels from the 7-token frames
        # Level 0: 1 code per frame (index 0)
        # Level 1: 2 codes per frame (indices 1, 4)
        # Level 2: 4 codes per frame (indices 2, 3, 5, 6)
        codes_0 = frames[:, 0].unsqueeze(0)
        codes_1 = torch.stack((frames[:, 1], frames[:, 4]), dim=1).flatten().unsqueeze(0)
        codes_2 = torch.stack((frames[:, 2], frames[:, 3], frames[:, 5], frames[:, 6]), dim=1).flatten().unsqueeze(0)

        codes = [codes_0, codes_1, codes_2]

        # Validate range (0..4096)
        for i, c in enumerate(codes):
            if torch.any(c < 0) or torch.any(c > 4096):
                logger.warning("SNAC codes out of range at level %d", i)
                return None

        with torch.inference_mode():
            audio_hat = model.decode(codes)

        # Convert to 16-bit PCM
        audio_np = audio_hat.squeeze().cpu().numpy()
        audio_int16 = (audio_np * 32767).clip(-32768, 32767).astype(np.int16)
        return audio_int16.tobytes()

    except Exception as e:
        logger.error("SNAC decoding failed: %s", e)
        return None


def decode_text_to_audio(text: str) -> Optional[bytes]:
    """Convenience: extract tokens from text and decode to audio in one step."""
    token_ids = extract_token_ids(text)
    if not token_ids:
        return None
    return decode_tokens(token_ids)


# Sample rate for SNAC output audio
SAMPLE_RATE = 24000
