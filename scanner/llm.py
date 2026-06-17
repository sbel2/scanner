"""
llm.py — LLM completion wrapper with multi-account token rotation.

Authentication uses Claude Code's long-lived OAuth token(s), generated once per
account with:

    claude setup-token

Each token draws from a Claude Pro/Max subscription's quota. A single daily run
fires dozens of LLM calls (one per opportunity scored, plus watch-page parsing),
which can exhaust one account's 5-hour session limit partway through. When that
happens this wrapper rotates to the next configured account and retries, so one
exhausted subscription doesn't sink the whole digest.

Configure one or more tokens in .env (priority order, top first):

    CLAUDE_CODE_OAUTH_TOKEN=<token-from-account-1>
    CLAUDE_CODE_OAUTH_TOKEN_2=<token-from-account-2>
    # ...up to CLAUDE_CODE_OAUTH_TOKEN_9

(You may also place several comma-separated tokens in CLAUDE_CODE_OAUTH_TOKEN.)

Fallback: if no OAuth token is set but ANTHROPIC_API_KEY is, the official
Anthropic SDK is used (pay-per-token billing — no rotation needed).
"""
from __future__ import annotations

import os


class SessionLimitError(RuntimeError):
    """An account's Claude subscription hit its session / usage limit.

    `reset_text` is the human-readable reason from the CLI, e.g.
    "You've hit your session limit · resets 1:10pm (America/New_York)".
    """

    def __init__(self, reset_text: str):
        super().__init__(reset_text)
        self.reset_text = reset_text


# Tokens (full value) that have hit their session limit during this process,
# mapped to the reset text the CLI reported. Skipped on subsequent calls so we
# don't waste a round-trip re-hitting a known-exhausted account each time.
_exhausted: dict[str, str] = {}


def _discover_tokens() -> list[str]:
    """Collect OAuth tokens in priority order from the environment.

    Reads CLAUDE_CODE_OAUTH_TOKEN (which may itself hold several comma- or
    whitespace-separated tokens) followed by CLAUDE_CODE_OAUTH_TOKEN_2.._9.
    Blanks and duplicates are dropped while preserving order.
    """
    raw: list[str] = []
    raw.extend(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").replace(",", " ").split())
    for n in range(2, 10):
        val = os.environ.get(f"CLAUDE_CODE_OAUTH_TOKEN_{n}", "").strip()
        if val:
            raw.append(val)

    seen: set[str] = set()
    tokens: list[str] = []
    for t in raw:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            tokens.append(t)
    return tokens


def _is_session_limit(text: str | None) -> bool:
    """True if an error result's text describes a subscription quota limit.

    Covers the 5-hour session limit and the weekly limit, both of which the CLI
    reports with a "resets <time>" suffix.
    """
    t = (text or "").lower()
    if "session limit" in t or "usage limit" in t or "weekly limit" in t:
        return True
    return "limit" in t and "reset" in t


def _mask(token: str) -> str:
    return (token[:10] + "…") if len(token) > 10 else "token"


def complete(system: str, user: str, model: str) -> str:
    """Send a single system+user message and return the assistant's text response.

    Rotates across configured OAuth tokens, skipping any that already hit their
    session limit during this run. Raises SessionLimitError only when every
    configured account is exhausted.
    """
    # Primary: Claude Code OAuth token(s) — the recommended path for users with
    # a Claude Pro/Max subscription.
    tokens = _discover_tokens()
    if tokens:
        for token in tokens:
            if token in _exhausted:
                continue
            try:
                return _complete_agent_sdk(system, user, model, token)
            except SessionLimitError as e:
                _exhausted[token] = e.reset_text
                print(
                    f"[llm] account {_mask(token)} hit its session limit "
                    f"({e.reset_text}); rotating to next account"
                )
                continue

        # Every configured account is exhausted.
        details = "; ".join(sorted(set(_exhausted.values()))) or "all accounts exhausted"
        raise SessionLimitError(
            f"All {len(tokens)} Claude account(s) have hit their session limit. {details}"
        )

    # Fallback: Anthropic API key (standard pay-per-token billing).
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return _complete_anthropic(system, user, model, api_key)

    raise RuntimeError(
        "No Claude authentication found.\n"
        "  Option 1 (recommended — uses your Claude subscription):\n"
        "    1. Install Claude Code: https://claude.ai/download\n"
        "    2. Run: claude setup-token\n"
        "    3. Copy the token into your .env as: CLAUDE_CODE_OAUTH_TOKEN=<token>\n"
        "       (add more accounts as CLAUDE_CODE_OAUTH_TOKEN_2, _3, ... to rotate)\n"
        "\n"
        "  Option 2 (API key — pay-per-token billing):\n"
        "    Set ANTHROPIC_API_KEY in your .env file.\n"
        "    Get a key at: https://console.anthropic.com/"
    )


def _complete_agent_sdk(system: str, user: str, model: str, oauth_token: str) -> str:
    """Use claude-agent-sdk with a long-lived OAuth token.

    Raises SessionLimitError when the account is out of quota so complete() can
    rotate; re-raises any other SDK error unchanged.
    """
    import asyncio

    # Set the token so the spawned CLI picks it up for this request.
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
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
            # 3 turns: tools are fully disabled below, so the model can't take
            # action — extra turns just give Haiku room to think + emit JSON
            # without hitting "Reached maximum number of turns (1)" mid-response,
            # which was silently breaking the freshness/eligibility checks.
            max_turns=3,
            allowed_tools=[],
            disallowed_tools=["*"],
            permission_mode="default",
        )
        chunks: list[str] = []
        result: ResultMessage | None = None
        sdk_error: Exception | None = None
        try:
            async for msg in query(prompt=user, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                elif isinstance(msg, ResultMessage):
                    result = msg
        except Exception as e:
            # The CLI exits non-zero after an is_error result; the SDK surfaces
            # that as a generic exception that masks the real reason. We already
            # captured the structured ResultMessage above, so inspect it first.
            sdk_error = e

        if result is not None and result.is_error and _is_session_limit(result.result):
            raise SessionLimitError((result.result or "session limit reached").strip())
        if sdk_error is not None:
            raise sdk_error
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
