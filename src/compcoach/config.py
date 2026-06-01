import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _optional_base_url(name: str) -> str | None:
    """
    Return a base URL or None. Empty values are removed from os.environ so the
    OpenAI SDK does not pick up OPENAI_BASE_URL= from .env as an invalid URL.
    """
    value = _env(name)
    if not value:
        os.environ.pop(name, None)
        return None
    if not value.startswith(("http://", "https://")):
        raise ValueError(
            f"{name} must start with http:// or https:// (got {value!r}). "
            "Leave it unset to use the default OpenAI API endpoint."
        )
    return value.rstrip("/")


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
PROMPTS_DIR = ROOT / "prompts"
USERS_PATH = DATA_DIR / "users.json"
COURSES_PATH = DATA_DIR / "courses.json"

OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_BASE_URL = _optional_base_url("OPENAI_BASE_URL")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")

CHROMA_PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma")))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "compcoach.db")))
AUDIT_LOG_DIR = Path(os.getenv("AUDIT_LOG_DIR", str(DATA_DIR / "audit")))

COURSES_COLLECTION = "courses"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
