import sys
from pathlib import Path

# Automatically add task3-digest directory to sys.path so tests import cleanly from anywhere
task3_dir = Path(__file__).resolve().parent.parent
if str(task3_dir) not in sys.path:
    sys.path.insert(0, str(task3_dir))
