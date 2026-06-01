#!/usr/bin/env python3
"""Build or rebuild the ChromaDB course index from data/courses.json."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from compcoach.rag.indexer import build_course_index  # noqa: E402

if __name__ == "__main__":
    n = build_course_index()
    print(f"Indexed {n} course summary chunks.")
