"""Atlas Cortex pipeline orchestration.

Exports :func:`run_pipeline` which sequences Layers 0-3 and handles
interaction logging.
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncGenerator

from cortex.providers.base import LLMProvider
from cortex.safety import (
    ConversationDriftMonitor,
    InputGuardrails,
    OutputGuardrails,
    Severity,
    build_safety_system_prompt,
    log_guardrail_event,
    resolve_content_tier,
)

from .layer0_context import assemble_context
from .layer1_instant import try_instant_answer
from .layer2_plugins import try_plugin_dispatch
from .layer3_llm import stream_llm_response

logger = logging.getLogger(__name__)


async def run_pipeline(
    message: str,
    provider: LLMProvider,
    user_id: str = "default",
    speaker_id: str | None = None,
    satellite_id: str | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    model_fast: str = "qwen2.5:14b",
    model_thinking: str = "qwen3:30b-a3b",
    system_prompt: str = "",
    memory_context: str = "",
    db_conn: Any = None,
    user_profile: dict[str, Any] | None = None,
    drift_monitor: ConversationDriftMonitor | None = None,
) -> AsyncGenerator[str, None]:
    """Run the full Atlas Cortex pipeline for a single message.

    Yields text tokens as soon as they are available.

    Input guardrails → Layer 0 → Layer 1 → Layer 2 → Layer 3 → Output guardrails
    """
    return _pipeline_generator(
        message=message,
        provider=provider,
        user_id=user_id,
        speaker_id=speaker_id,
        satellite_id=satellite_id,
        conversation_history=conversation_history,
        metadata=metadata,
        model_fast=model_fast,
        model_thinking=model_thinking,
        system_prompt=system_prompt,
        memory_context=memory_context,
        db_conn=db_conn,
        user_profile=user_profile,
        drift_monitor=drift_monitor,
    )


async def _pipeline_generator(
    message: str,
    provider: LLMProvider,
    user_id: str,
    speaker_id: str | None,
    satellite_id: str | None,
    conversation_history: list[dict[str, Any]] | None,
    metadata: dict[str, Any] | None,
    model_fast: str,
    model_thinking: str,
    system_prompt: str,
    memory_context: str,
    db_conn: Any,
    user_profile: dict[str, Any] | None = None,
    drift_monitor: ConversationDriftMonitor | None = None,
) -> AsyncGenerator[str, None]:
    start_ms = int(time.monotonic() * 1000)

    profile = user_profile or {}
    content_tier = resolve_content_tier(profile)
    input_guards = InputGuardrails(db_conn)
    output_guards = OutputGuardrails()

    # ── Input Guardrails ──────────────────────────────────────
    input_result = input_guards.check(message, profile, content_tier)
    if drift_monitor is not None:
        drift_monitor.update(int(input_result.severity))

    if input_result.severity >= Severity.SOFT_BLOCK:
        safe_response = input_result.suggested_response or (
            "I'm not able to help with that request."
        )
        log_guardrail_event(
            db_conn,
            user_id=user_id,
            direction="input",
            result=input_result,
            action_taken="blocked",
            content_tier=content_tier,
            trigger_text=message,
        )
        yield safe_response
        return

    if input_result.severity == Severity.WARN:
        log_guardrail_event(
            db_conn,
            user_id=user_id,
            direction="input",
            result=input_result,
            action_taken="warned",
            content_tier=content_tier,
            trigger_text=message,
        )

    # ── Build safety system prompt ────────────────────────────
    drift_context = drift_monitor.get_safety_context() if drift_monitor else ""
    safety_prompt = build_safety_system_prompt(content_tier, drift_context)
    # Prepend safety prompt; callers may supply additional prompt text
    effective_system_prompt = (
        safety_prompt + ("\n\n" + system_prompt if system_prompt else "")
    )

    # ── Layer 0: Context Assembly ─────────────────────────────
    context = await assemble_context(
        message=message,
        user_id=user_id,
        speaker_id=speaker_id,
        satellite_id=satellite_id,
        conversation_history=conversation_history,
        metadata=metadata,
    )

    # ── Layer 1: Instant Answers ─────────────────────────────
    instant_response, instant_confidence = await try_instant_answer(message, context)
    if instant_response is not None:
        # Instant answers are safe by construction but still pass output guards
        out_result = output_guards.check(
            instant_response, profile, content_tier,
            effective_system_prompt, message
        )
        if out_result.severity >= Severity.SOFT_BLOCK:
            instant_response = out_result.suggested_response or instant_response
            log_guardrail_event(
                db_conn, user_id=user_id, direction="output",
                result=out_result, action_taken="replaced",
                content_tier=content_tier, trigger_text=instant_response,
            )
        yield instant_response
        _log_interaction(
            db_conn, context, message, instant_response,
            matched_layer="instant",
            confidence=instant_confidence,
            response_time_ms=int(time.monotonic() * 1000) - start_ms,
        )
        return

    # ── Layer 2: Plugin Dispatch ──────────────────────────────
    plugin_response, plugin_confidence, entities = await try_plugin_dispatch(message, context)
    if plugin_response is not None:
        out_result = output_guards.check(
            plugin_response, profile, content_tier,
            effective_system_prompt, message
        )
        if out_result.severity >= Severity.SOFT_BLOCK:
            plugin_response = out_result.suggested_response or plugin_response
            log_guardrail_event(
                db_conn, user_id=user_id, direction="output",
                result=out_result, action_taken="replaced",
                content_tier=content_tier, trigger_text=plugin_response,
            )
        yield plugin_response
        _log_interaction(
            db_conn, context, message, plugin_response,
            matched_layer="tool",
            confidence=plugin_confidence,
            entities_used=entities,
            response_time_ms=int(time.monotonic() * 1000) - start_ms,
        )
        return

    # ── Layer 3: Filler + LLM (buffer before output guardrail check) ──
    full_response_parts: list[str] = []
    async for chunk in stream_llm_response(
        message=message,
        context=context,
        provider=provider,
        model_fast=model_fast,
        model_thinking=model_thinking,
        memory_context=memory_context,
        system_prompt=effective_system_prompt,
    ):
        full_response_parts.append(chunk)

    full_response = "".join(full_response_parts)

    # ── Output Guardrails ─────────────────────────────────────
    out_result = output_guards.check(
        full_response, profile, content_tier,
        effective_system_prompt, message,
    )
    if out_result.severity >= Severity.SOFT_BLOCK:
        safe_response = out_result.suggested_response or (
            "I'm not able to provide that response."
        )
        log_guardrail_event(
            db_conn, user_id=user_id, direction="output",
            result=out_result, action_taken="replaced",
            content_tier=content_tier, trigger_text=full_response,
        )
        yield safe_response
        full_response = safe_response
    else:
        yield full_response
        if out_result.severity == Severity.WARN:
            log_guardrail_event(
                db_conn, user_id=user_id, direction="output",
                result=out_result, action_taken="warned",
                content_tier=content_tier, trigger_text=full_response,
            )

    if drift_monitor is not None:
        drift_monitor.update(int(out_result.severity))

    _log_interaction(
        db_conn, context, message, full_response,
        matched_layer="llm",
        confidence=0.0,  # Will be updated by grounding layer
        response_time_ms=int(time.monotonic() * 1000) - start_ms,
    )


def _log_interaction(
    conn: Any,
    context: dict[str, Any],
    message: str,
    response: str,
    matched_layer: str,
    confidence: float,
    response_time_ms: int = 0,
    entities_used: list[str] | None = None,
) -> None:
    """Persist an interaction to SQLite (best-effort, never raises)."""
    if conn is None:
        return
    try:
        cur = conn.execute(
            """
            INSERT INTO interactions
              (user_id, speaker_id, message, matched_layer, sentiment,
               sentiment_score, response, response_time_ms, confidence_score,
               resolved_area)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                context.get("user_id"),
                context.get("speaker_id"),
                message,
                matched_layer,
                context.get("sentiment"),
                context.get("sentiment_score"),
                response[:4000],  # cap to avoid huge blobs
                response_time_ms,
                confidence,
                context.get("room"),
            ),
        )
        interaction_id = cur.lastrowid
        # Log entity refs for Layer 2
        for entity_id in (entities_used or []):
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO interaction_entities (interaction_id, entity_id) VALUES (?, ?)",
                    (interaction_id, entity_id),
                )
            except Exception:
                pass
        conn.commit()
    except Exception as exc:
        logger.debug("Interaction logging failed: %s", exc)
