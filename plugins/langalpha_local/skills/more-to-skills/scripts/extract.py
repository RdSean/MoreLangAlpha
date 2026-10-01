#!/usr/bin/env python3
"""
Extract text from a document file for more-to-skills processing.
Backward-compatible entrypoint wrapper.
"""

import os
import sys

# Force UTF-8 stdout/stderr so extracted text, the attribution line's separators
# and the dependency-check glyphs (✓ / ✗) don't raise UnicodeEncodeError on Windows
# consoles that default to a legacy code page (e.g. GBK / cp936).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Ensure the project root directory (where the 'more_to_skills' package lives) is in sys.path
# so the modular package can be imported reliably regardless of the working directory.
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from more_to_skills.cli import main

if __name__ == "__main__":
    main()
