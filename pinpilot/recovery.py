"""Bounded recovery decisions for autonomous campaign operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str
    approval_required: bool = False


class RecoveryController:
    """Classify failures without hiding critical or irreversible errors."""

    _approval_markers = (
        "payment", "billing", "insufficient balance", "publish", "credential",
        "secret", "delete", "401", "403", "authentication", "access token",
    )
    _retry_markers = (
        "timeout", "timed out", "rate limit", "429", "temporarily unavailable",
        "connection", "502", "503", "504", "prompt is too long", "4000 characters",
        "invalid json", "valid structured json", "no valid structured json",
        "invalid file", "file not found", "dropbox", "pinterest", "gumroad",
    )

    @classmethod
    def decide(cls, error: BaseException, attempt: int, max_attempts: int) -> RecoveryDecision:
        message = str(error).lower()
        if "payment" in message or "billing" in message or "insufficient balance" in message:
            return RecoveryDecision("stop", "Payment or provider credit issue requires user approval.", True)
        if "publish" in message or "delete" in message:
            return RecoveryDecision("stop", "Irreversible external action requires user approval.", True)
        if any(marker in message for marker in ("credential", "secret", "401", "403", "authentication", "access token")):
            return RecoveryDecision("stop", "Critical or irreversible action requires user approval.", True)
        if "prompt is too long" in message or "4000 characters" in message:
            return RecoveryDecision("compact_prompt", "Provider rejected the prompt size.")
        if any(marker in message for marker in cls._retry_markers) and attempt < max_attempts - 1:
            return RecoveryDecision("retry", "Transient provider or network failure.")
        if attempt >= max_attempts - 1:
            return RecoveryDecision("stop", "Repeated failure requires user approval.", True)
        return RecoveryDecision("stop", "Failure was not safely recoverable.")

    @staticmethod
    def compact_prompt(prompt: str, limit: int = 3000) -> str:
        if len(prompt) <= limit:
            return prompt
        return prompt[:limit].rstrip() + "\n[Context compacted by recovery controller.]"

    @staticmethod
    def provider_fallback(config: Any, provider: str) -> str | None:
        if provider == "openrouter" and getattr(config.agent, "huggingface_token", ""):
            return "huggingface"
        if provider == "novita" and getattr(config.agent, "huggingface_token", ""):
            return "huggingface"
        return None
