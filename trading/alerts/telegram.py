"""Telegram dispatch helper for MarkdownV2 messages."""

from __future__ import annotations

from typing import Any

import requests


class TelegramDispatchError(RuntimeError):
    """Raised when Telegram API delivery fails."""


def send_markdown_v2_messages(
    messages: list[str],
    *,
    token: str,
    chat_id: str,
    disable_web_page_preview: bool = True,
    timeout_seconds: float = 10.0,
) -> list[dict[str, Any]]:
    """Send one or more messages through Telegram Bot API."""
    if not token:
        raise TelegramDispatchError("Telegram token is required")
    if not chat_id:
        raise TelegramDispatchError("Telegram chat_id is required")

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    responses: list[dict[str, Any]] = []

    for message in messages:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": disable_web_page_preview,
        }
        response = requests.post(endpoint, json=payload, timeout=timeout_seconds)
        if response.status_code != 200:
            raise TelegramDispatchError(
                f"Telegram API error {response.status_code}: {response.text[:200]}"
            )
        decoded = response.json()
        if not isinstance(decoded, dict) or not decoded.get("ok"):
            raise TelegramDispatchError(f"Telegram API returned non-ok payload: {decoded}")
        responses.append(decoded)

    return responses
