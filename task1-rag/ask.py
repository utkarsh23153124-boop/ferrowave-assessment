"""Ask one or more questions without the HTTP server: python ask.py "question" ["another"]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag.answer import Answerer  # noqa: E402
from rag.retrieve import Index  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    answerer = Answerer(Index())
    for q in argv:
        res = answerer.ask(q)
        print(json.dumps({"question": q, **res}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
