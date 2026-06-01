"""Load system prompt sections from the prompts/ directory."""

from pathlib import Path
from typing import Any

from compcoach.config import PROMPTS_DIR
from compcoach.profile import profile_json, profile_summary

_SECTION_FILES = (
    "role.md",
    "navigation.md",
    "scope.md",
    "boundaries.md",
    "safety.md",
    "opening.md",
    "conversation.md",
)


def _read(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt file: {path}")
    return path.read_text(encoding="utf-8").strip()


def load_opening_user_message() -> str:
    return _read("opening_user_message.txt")


def build_system_prompt(display_name: str, profile: dict[str, Any]) -> str:
    parts = [_read(name) for name in _SECTION_FILES]
    user_block = (
        f"## User\n\n"
        f"Name: {display_name}\n\n"
        f"### Profile summary\n\n"
        f"{profile_summary(profile)}\n\n"
        f"### Full profile (JSON)\n\n"
        f"{profile_json(profile)}"
    )
    # role, then user data, then rules (navigation early in files but user context in middle)
    return "\n\n".join([parts[0], user_block, *parts[1:]])
