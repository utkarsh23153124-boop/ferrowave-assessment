"""Entry point: python ingest.py --corpus ../corpus"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag.ingest import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
