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

from fastapi import FastAPI, Header, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
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

        # ingest decides on its own whether a key is available and degrades to BM25 if not
        if ingest_main(["--corpus", str(DEFAULT_CORPUS)]) != 0:
            raise RuntimeError(f"could not build an index from {DEFAULT_CORPUS}")
    _load()
    yield


def _allowed_corpus(raw: Optional[str]) -> Path:
    """Reindex only from directories inside the repository, so an unauthenticated client
    cannot point the service at arbitrary files on the host."""
    from rag.config import REPO_ROOT

    corpus = Path(raw).expanduser() if raw else DEFAULT_CORPUS
    corpus = (REPO_ROOT / corpus).resolve() if not corpus.is_absolute() else corpus.resolve()
    if REPO_ROOT.resolve() not in corpus.parents and corpus != REPO_ROOT.resolve():
        raise HTTPException(status_code=403, detail="corpus must be a directory inside the repository")
    if not (corpus / "_manifest.csv").exists():
        raise HTTPException(status_code=400, detail=f"no _manifest.csv in {corpus}")
    return corpus


app = FastAPI(title="Ferrowave Pulse answer engine", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ReindexRequest(BaseModel):
    corpus: Optional[str] = None
    embed: bool = True


STATIC = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def home():
    """Minimal browser UI for asking questions."""
    return FileResponse(STATIC, media_type="text/html")


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
def reindex(req: ReindexRequest, x_admin_token: Optional[str] = Header(default=None)):
    """Rebuild the index from a corpus path inside the repo and reload it without restarting.
    If RAG_ADMIN_TOKEN is set in the environment, the X-Admin-Token header must match it."""
    from rag.ingest import main as ingest_main

    expected = os.getenv("RAG_ADMIN_TOKEN")
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=401, detail="missing or wrong X-Admin-Token")
    corpus = _allowed_corpus(req.corpus)
    args = ["--corpus", str(corpus)]
    if not req.embed:
        args.append("--no-embed")
    try:
        rc = ingest_main(args)
    except Exception as exc:  # the old index is untouched: ingest builds into a temp dir
        raise HTTPException(status_code=502, detail=f"ingest failed, previous index kept: {type(exc).__name__}: {exc}") from exc
    if rc != 0:
        raise HTTPException(status_code=400, detail=f"ingest refused corpus {corpus} (see server log); previous index kept")
    _load()
    return health()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), reload=False)
