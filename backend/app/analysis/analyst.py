"""Analyst: structured-output Claude calls for the model cascade.

Triage (cheap model) gates relevance; analysis produces a full ForecastOutput
with a caller-selectable model so the pipeline can run its Sonnet-default /
Opus-escalation / shadow-comparison cascade through one code path.

Uses the sync Anthropic client (messages.parse) wrapped in asyncio.to_thread so
the async scheduler never blocks. System prompts are frozen constants with a
cache_control breakpoint. NOTE: at current prompt sizes (~700 / ~215 tokens)
the breakpoint is inert — minimum cacheable prefix is 2048 tokens on Sonnet
and 4096 on Haiku/Opus, below which it is a silent no-op. Harmless now;
becomes active automatically if the prompts grow past the threshold (verify
via response.usage.cache_read_input_tokens > 0).

All failures are caught and logged; functions return None instead of raising,
so the scheduler never crashes on API/network errors.
"""

import asyncio
import json
import logging
from typing import Any, NamedTuple

import anthropic
from pydantic import BaseModel

from app.analysis.prompts import SYSTEM_PROMPT, TRIAGE_PROMPT
from app.config import settings
from app.schemas import ForecastOutput, TriageOutput

logger = logging.getLogger(__name__)
_client: anthropic.Anthropic | None = None


class AnalystCall(NamedTuple):
    """One LLM call: parsed output (None on failure) plus real token usage,
    so the pipeline can ledger actual spend per call."""

    output: Any | None
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def ok(self) -> bool:
        return self.output is not None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def _structured_call(
    model: str,
    system_prompt: str,
    user_content: str,
    output_format: type[BaseModel],
    max_tokens: int = 2048,
) -> AnalystCall:
    try:
        response = _get_client().messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_content}],
            output_format=output_format,
        )
        usage = response.usage
        return AnalystCall(
            response.parsed_output, model, usage.input_tokens, usage.output_tokens
        )
    except anthropic.APIError as exc:
        logger.error("%s call (%s) failed: %s", output_format.__name__, model, exc)
        return AnalystCall(None, model)
    except Exception:
        logger.exception("%s call (%s) failed unexpectedly", output_format.__name__, model)
        return AnalystCall(None, model)


def triage_event_sync(event_payload: dict) -> AnalystCall:
    user_content = "Triage this event.\n\nEVENT:\n" + json.dumps(
        event_payload, default=str, indent=2
    )
    return _structured_call(
        settings.triage_model, TRIAGE_PROMPT, user_content, TriageOutput, max_tokens=512
    )


async def triage_event(event_payload: dict) -> AnalystCall:
    return await asyncio.to_thread(triage_event_sync, event_payload)


def analyze_event_sync(
    event_payload: dict, market_context: dict, model: str | None = None
) -> AnalystCall:
    user_content = (
        "Analyze this event and produce a forecast.\n\n"
        "EVENT:\n" + json.dumps(event_payload, default=str, indent=2)
        + "\n\nCURRENT MARKET CONTEXT:\n" + json.dumps(market_context, default=str, indent=2)
    )
    return _structured_call(
        model or settings.analyst_model, SYSTEM_PROMPT, user_content, ForecastOutput
    )


async def analyze_event(
    event_payload: dict, market_context: dict, model: str | None = None
) -> AnalystCall:
    return await asyncio.to_thread(analyze_event_sync, event_payload, market_context, model)
