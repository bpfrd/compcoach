import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from compcoach.config import DATABASE_PATH

DEFAULT_CHAT_TITLE = "Competence coaching session"
_DEFAULT_TITLE_RE = re.compile(
    rf"^{re.escape(DEFAULT_CHAT_TITLE)}(?: \((\d+)\))?$"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

CREATE INDEX IF NOT EXISTS idx_chats_username ON chats(username);
CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATABASE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def list_chats(self, username: str) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS msg_count
            FROM chats c
            WHERE c.username = ?
            ORDER BY c.updated_at DESC
            """,
            (username,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_chat(self, chat_id: int, username: str) -> dict | None:
        cur = self._conn.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chats
            WHERE id = ? AND username = ?
            """,
            (chat_id, username),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def next_default_chat_title(self, username: str) -> str:
        """
        First unnamed chat: 'Competence coaching session'.
        Further unnamed chats: 'Competence coaching session (1)', '(2)', ...
        """
        has_base = False
        numbered: list[int] = []
        for chat in self.list_chats(username):
            title = chat.get("title") or ""
            match = _DEFAULT_TITLE_RE.match(title)
            if not match:
                continue
            if match.group(1) is None:
                has_base = True
            else:
                numbered.append(int(match.group(1)))
        if not has_base:
            return DEFAULT_CHAT_TITLE
        next_n = max(numbered, default=0) + 1
        return f"{DEFAULT_CHAT_TITLE} ({next_n})"

    def create_chat(self, username: str, title: str | None = None) -> int:
        now = _now()
        if title is None or not str(title).strip():
            title = self.next_default_chat_title(username)
        else:
            title = str(title).strip()
        cur = self._conn.execute(
            "INSERT INTO chats (username, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (username, title, now, now),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def touch_chat(self, chat_id: int) -> None:
        self._conn.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (_now(), chat_id),
        )
        self._conn.commit()

    def get_messages(self, chat_id: int) -> list[dict]:
        cur = self._conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        )
        return [{"role": row["role"], "content": row["content"]} for row in cur.fetchall()]

    def save_messages(self, chat_id: int, messages: list[dict]) -> None:
        self._conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        now = _now()
        for msg in messages:
            if msg["role"] not in ("user", "assistant", "system"):
                continue
            self._conn.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, msg["role"], msg["content"], now),
            )
        self.touch_chat(chat_id)

    def replace_conversation(
        self, chat_id: int, messages: list[dict], *, include_system: bool = False
    ) -> None:
        """Persist user/assistant turns (and optionally system) for resume."""
        to_save = []
        for msg in messages:
            if msg["role"] == "system" and not include_system:
                continue
            if msg["role"] in ("user", "assistant", "system"):
                to_save.append(msg)
        self.save_messages(chat_id, to_save)
