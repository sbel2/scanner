"""
llm.py — LLM completion wrapper.

Supports two backends:
  1. Anthropic SDK (preferred for public use) — requires ANTHROPIC_API_KEY in .env
  2. claude-agent-sdk (fallback) — requires `claude` CLI to be logged in

The backend is selected automatically: if ANTHROPIC_API_KEY is set, the Anthropic
SDK is used. Otherwise, claude-agent-sdk is attempted.
"""
from __future__ import annotations

import os


def complete(system: str, user: str, model: str) -> str:
    """Send a single system+user message and return the assistant's text response."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return _complete_anthropic(system, user, model, api_key)
    else:
        return _complete_agent_sdk(system, user, model)


def _complete_anthropic(system: str, user: str, model: str, api_key: str) -> str:
    """Use the official Anthropic SDK."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        ) from e

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text.strip()


def _complete_agent_sdk(system: str, user: str, model: str) -> str:
    """Fallback: use claude-agent-sdk (requires `claude` CLI login)."""
    import asyncio

    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )
    except ImportError as e:
        raise RuntimeError(
            "Neither ANTHROPIC_API_KEY nor claude-agent-sdk is available.\n"
            "Set ANTHROPIC_API_KEY in your .env file, or install claude-agent-sdk."
        ) from e

    async def _run() -> str:
        options = ClaudeAgentOptions(
            system_prompt=system,
            model=model,
            max_turns=1,
            allowed_tools=[],
            disallowed_tools=["*"],
            permission_mode="default",
        )
        chunks: list[str] = []
        async for msg in query(prompt=user, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
        return "".join(chunks).strip()

    return asyncio.run(_run())
