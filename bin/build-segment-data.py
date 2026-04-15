#!/usr/bin/env python3
"""
CLI script for building segment data.
Delegates to segment_tools package.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from segment_tools.build_data import main

if __name__ == "__main__":
    main()
