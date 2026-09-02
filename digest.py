#!/usr/bin/env python3
"""
Root wrapper for Task 3: Weekly Insights Digest CLI.
Allows executing the CLI directly from the monorepo root as documented in CANDIDATE_BRIEF.md.
"""

import sys
from pathlib import Path

# Ensure task3-digest modules are resolvable
task3_dir = Path(__file__).resolve().parent / "task3-digest"
if str(task3_dir) not in sys.path:
    sys.path.insert(0, str(task3_dir))

from digest import main

if __name__ == "__main__":
    main()
