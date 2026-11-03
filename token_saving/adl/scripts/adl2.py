#!/usr/bin/env python3
"""ADL v2 tool entry point. Stdlib only, Python >= 3.8.

Usage: python3 adl2.py <command> ...   (python3 adl2.py --help)
Spec:  token_saving/adl2.md
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # never leave __pycache__ in an installed skill directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adl2lib.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
