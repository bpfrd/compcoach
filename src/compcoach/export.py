import json
import re
from datetime import datetime, timezone
from pathlib import Path

from compcoach.auth import User
from compcoach.config import DATA_DIR
from compcoach.db import ChatStore

EXPORTS_DIR = DATA_DIR / "exports"


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[-\s]+", "-", text).strip("-")
    return text[:60] or "chat"


def export_conversation(store: ChatStore, user: User, chat_id: int) -> tuple[Path, Path]:
    """
    Export a chat as JSON and Markdown. Returns paths to both files.
    Raises ValueError if the chat does not exist or belongs to another user.
    """
    chat = store.get_chat(chat_id, user.username)
    if chat is None:
        raise ValueError(f"Chat #{chat_id} was not found for your account.")

    messages = store.get_messages(chat_id)
    if not messages:
        raise ValueError(f"Chat #{chat_id} has no messages to export.")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base = f"chat-{chat_id}-{_slug(chat['title'])}-{stamp}"

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "username": user.username,
        "display_name": user.display_name,
        "chat": {
            "id": chat["id"],
            "title": chat["title"],
            "created_at": chat["created_at"],
            "updated_at": chat["updated_at"],
        },
        "messages": messages,
    }

    json_path = EXPORTS_DIR / f"{base}.json"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        f"# {chat['title']}",
        "",
        f"- **Chat ID:** {chat_id}",
        f"- **User:** {user.display_name} ({user.username})",
        f"- **Exported:** {payload['exported_at']}",
        f"- **Created:** {chat['created_at']}",
        f"- **Updated:** {chat['updated_at']}",
        "",
        "---",
        "",
    ]
    for msg in messages:
        role = msg["role"]
        label = "You" if role == "user" else "CompCoach"
        md_lines.append(f"## {label}")
        md_lines.append("")
        md_lines.append(msg["content"])
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_path = EXPORTS_DIR / f"{base}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return json_path, md_path
