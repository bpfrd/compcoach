"""Recognize the in-chat navigation command so it is never sent to the LLM."""

from typing import Literal

ChatCommand = Literal["menu"]


def normalize_user_input(raw: str) -> str:
    """Normalize for command detection: trim, lowercase, \\ -> /."""
    return raw.strip().lower().replace("\\", "/")


def parse_chat_command(raw: str) -> ChatCommand | None:
    """
    In chat, only /menu returns to the main menu (\\menu is accepted too).
    Any other input — including q, exit, /exit — is normal chat for the LLM.
    """
    if normalize_user_input(raw) == "/menu":
        return "menu"
    return None
