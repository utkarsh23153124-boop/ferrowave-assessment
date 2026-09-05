"""Task 1 answer service.

    python app.py                 # serve on http://127.0.0.1:8000
    python ingest.py --corpus ../corpus   # rebuild the index, then restart (or POST /reindex)
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from rag.answer import Answerer  # noqa: E402
from rag.config import CHAT_MODEL, DEFAULT_CORPUS, INDEX_DIR, load_env  # noqa: E402
from rag.retrieve import Index  # noqa: E402

state: dict = {}


def _load() -> None:
    index = Index(INDEX_DIR)
    state["index"] = index
    state["answerer"] = Answerer(index)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_env()
    if not (INDEX_DIR / "meta.json").exists():
        print("No index found; building it from", DEFAULT_CORPUS, file=sys.stderr)
        from rag.ingest import main as ingest_main

        ingest_main(["--corpus", str(DEFAULT_CORPUS)])
    _load()
    yield


app = FastAPI(title="Ferrowave Pulse answer engine", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ReindexRequest(BaseModel):
    corpus: Optional[str] = None
    embed: bool = True


@app.get("/health")
def health():
    index: Index = state["index"]
    return {
        "ok": True,
        "documents_indexed": index.meta["documents_customer_visible"],
        "model": CHAT_MODEL,
        "documents_total": index.meta["documents"],
        "chunks": index.meta["chunks"],
        "embeddings": index.faiss is not None,
        "index_built_at": index.meta["built_at"],
    }


@app.post("/ask")
def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question is empty")
    try:
        return state["answerer"].ask(question)
    except Exception as exc:  # surface as a clean 502 rather than a stack trace
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/reindex")
def reindex(req: ReindexRequest):
    """Rebuild the index from a corpus path and reload it without restarting."""
    from rag.ingest import main as ingest_main

    corpus = req.corpus or str(DEFAULT_CORPUS)
    args = ["--corpus", corpus]
    if not req.embed:
        args.append("--no-embed")
    rc = ingest_main(args)
    if rc != 0:
        raise HTTPException(status_code=400, detail=f"ingest failed for corpus {corpus}")
    _load()
    return health()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), reload=False)
