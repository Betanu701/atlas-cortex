"""ReSpeaker 2-mic HAT button handler.

The ReSpeaker 2-mic HAT has a tactile button on GPIO 17 (BCM).
Active LOW with internal pull-up (1 = not pressed, 0 = pressed).

Three modes controlled by ``button_mode`` config:

  ``toggle``  — Press toggles wake-word listening on/off (default).
                LED shows muted pattern when wake word is disabled.
  ``press``   — Single press starts listening (like saying the wake word).
                Satellite returns to IDLE after processing.
  ``hold``    — Hold to speak (intercom style).  Listening starts on
                press-down, ends on release.

The mode is configurable via admin portal or ``config.json``.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

_HAS_GPIO = False
try:
    import RPi.GPIO as GPIO
    _HAS_GPIO = True
except ImportError:
    GPIO = None  # type: ignore[assignment]

BUTTON_PIN = 17  # BCM pin number on ReSpeaker 2-mic HAT
DEBOUNCE_MS = 200  # Debounce time to prevent double triggers


class ButtonHandler:
    """Handles ReSpeaker button GPIO events."""

    def __init__(self, mode: str = "toggle") -> None:
        self.mode = mode  # toggle | press | hold
        self._on_press = None  # callback: async def on_press()
        self._on_release = None  # callback: async def on_release()
        self._on_toggle = None  # callback: async def on_toggle(enabled: bool)
        self._enabled = True  # For toggle mode: is wake word active?
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_event = 0.0
        self._active = False

    def register(
        self,
        on_press=None,
        on_release=None,
        on_toggle=None,
    ) -> None:
        """Register async callbacks for button events."""
        self._on_press = on_press
        self._on_release = on_release
        self._on_toggle = on_toggle

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start listening for button events on GPIO 17."""
        if not _HAS_GPIO:
            logger.warning("RPi.GPIO not available — button disabled")
            return

        self._loop = loop
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                BUTTON_PIN, GPIO.BOTH,
                callback=self._gpio_callback,
                bouncetime=DEBOUNCE_MS,
            )
            self._active = True
            logger.info("Button handler started (GPIO %d, mode=%s)", BUTTON_PIN, self.mode)
        except Exception as e:
            logger.warning("Failed to set up button GPIO: %s", e)

    def stop(self) -> None:
        """Clean up GPIO resources."""
        if not _HAS_GPIO or not self._active:
            return
        try:
            GPIO.remove_event_detect(BUTTON_PIN)
            GPIO.cleanup(BUTTON_PIN)
        except Exception:
            pass
        self._active = False

    def _gpio_callback(self, channel: int) -> None:
        """GPIO interrupt callback — runs in GPIO thread, schedules async."""
        now = time.monotonic()
        if now - self._last_event < DEBOUNCE_MS / 1000:
            return
        self._last_event = now

        if not self._loop:
            return

        pressed = GPIO.input(BUTTON_PIN) == 0  # Active LOW

        if self.mode == "toggle":
            if pressed:  # Only act on press-down
                self._enabled = not self._enabled
                logger.info("Button toggle: wake word %s",
                            "enabled" if self._enabled else "disabled")
                if self._on_toggle:
                    asyncio.run_coroutine_threadsafe(
                        self._on_toggle(self._enabled), self._loop)

        elif self.mode == "press":
            if pressed:  # Single press → start listening
                logger.info("Button press: start listening")
                if self._on_press:
                    asyncio.run_coroutine_threadsafe(
                        self._on_press(), self._loop)

        elif self.mode == "hold":
            if pressed:
                logger.info("Button hold: start listening")
                if self._on_press:
                    asyncio.run_coroutine_threadsafe(
                        self._on_press(), self._loop)
            else:
                logger.info("Button release: stop listening")
                if self._on_release:
                    asyncio.run_coroutine_threadsafe(
                        self._on_release(), self._loop)

    @property
    def wake_word_enabled(self) -> bool:
        """In toggle mode, returns whether wake word is currently active."""
        if self.mode != "toggle":
            return True
        return self._enabled
