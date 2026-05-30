"""
llm.py — LLM completion wrapper.

Authentication uses Claude Code's long-lived OAuth token, generated once with:

    claude setup-token

This produces a 1-year token that is stored in CLAUDE_CODE_OAUTH_TOKEN in your .env.
It draws from your Claude Pro/Max subscription — no separate API billing needed.

Fallback: if ANTHROPIC_API_KEY is set instead, the official Anthropic SDK is used.
"""
from __future__ import annotations

import os


def complete(system: str, user: str, model: str) -> str:
    """Send a single system+user message and return the assistant's text response."""
    # Primary: Claude Code OAuth token (claude-agent-sdk)
    # This is the recommended path for users with a Claude Pro/Max subscription.
    oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    if oauth_token:
        return _complete_agent_sdk(system, user, model, oauth_token)

    # Fallback: Anthropic API key (standard pay-per-token billing)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return _complete_anthropic(system, user, model, api_key)

    raise RuntimeError(
        "No Claude authentication found.\n"
        "  Option 1 (recommended — uses your Claude subscription):\n"
        "    1. Install Claude Code: https://claude.ai/download\n"
        "    2. Run: claude setup-token\n"
        "    3. Copy the token into your .env as: CLAUDE_CODE_OAUTH_TOKEN=<token>\n"
        "\n"
        "  Option 2 (API key — pay-per-token billing):\n"
        "    Set ANTHROPIC_API_KEY in your .env file.\n"
        "    Get a key at: https://console.anthropic.com/"
    )


def _complete_agent_sdk(system: str, user: str, model: str, oauth_token: str) -> str:
    """Use claude-agent-sdk with a long-lived OAuth token."""
    import asyncio
    import os

    # Set the token so the SDK picks it up automatically
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            TextBlock,
            query,
        )
    except ImportError as e:
        raise RuntimeError(
            "claude-agent-sdk is not installed. Run: pip install claude-agent-sdk"
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


def _complete_anthropic(system: str, user: str, model: str, api_key: str) -> str:
    """Fallback: use the official Anthropic SDK with a pay-per-token API key."""
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
