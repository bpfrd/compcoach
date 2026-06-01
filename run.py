#!/usr/bin/env python3
"""Start the CompCoach shell chat (prototype entry point)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from compcoach.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
