#!/usr/bin/env python3
"""
CLI script for generating segment videos.
Delegates to segment_tools package.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from segment_tools.generate_videos import main

if __name__ == "__main__":
    main()
