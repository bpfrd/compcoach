import json
from dataclasses import dataclass
from typing import Any

from compcoach.config import USERS_PATH


@dataclass
class User:
    username: str
    display_name: str
    profile: dict[str, Any]


def _load_users_raw() -> list[dict]:
    with open(USERS_PATH, encoding="utf-8") as f:
        return json.load(f)


def authenticate(username: str, password: str) -> User | None:
    username = username.strip()
    for row in _load_users_raw():
        if row["username"] != username:
            continue
        if row.get("initial_password") != password:
            return None
        return User(
            username=row["username"],
            display_name=row.get("display_name", username),
            profile=row["profile"],
        )
    return None


def get_user(username: str) -> User | None:
    for row in _load_users_raw():
        if row["username"] == username:
            return User(
                username=row["username"],
                display_name=row.get("display_name", username),
                profile=row["profile"],
            )
    return None
