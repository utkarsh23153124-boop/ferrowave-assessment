"""Hybrid retrieval: BM25 + FAISS fused by LangChain's EnsembleRetriever, then re-ranked
by authority tier from policy.py. Only customer-visible chunks are searched."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from .config import EMBED_MODEL, INDEX_DIR, RETRIEVE_K, TOP_K, load_env
from .ingest import CHUNKS_FILE, EXTRACTED_DIR, FAISS_DIR, META_FILE, header_for
from .policy import weight_for_tier

_WORD = __import__("re").compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    return _WORD.findall(text.lower())


class Index:
    """Everything loaded from index/: chunks, metadata, BM25, FAISS (if built)."""

    def __init__(self, index_dir: Path = INDEX_DIR, use_embeddings: Optional[bool] = None):
        self.index_dir = Path(index_dir)
        self.meta: Dict = json.loads((self.index_dir / META_FILE).read_text(encoding="utf-8"))
        self.docs: List[Document] = []
        with (self.index_dir / CHUNKS_FILE).open(encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                self.docs.append(Document(page_content=rec["text"], metadata=rec["metadata"]))
        self.visible = [d for d in self.docs if d.metadata.get("customer_visible")]
        self.by_id = {d.metadata["chunk_id"]: d for d in self.docs}

        # BM25 over title+section+text so short chunks (table rows, FAQ pairs) carry context.
        corpus_tokens = [tokenize(header_for(d)) for d in self.visible]
        self.bm25 = BM25Retriever(vectorizer=BM25Okapi(corpus_tokens), docs=self.visible, k=RETRIEVE_K,
                                  preprocess_func=tokenize)

        self.embeddings = None
        self.faiss: Optional[FAISS] = None
        want = self.meta.get("embedded", False) if use_embeddings is None else use_embeddings
        if want and (self.index_dir / FAISS_DIR).exists():
            from langchain_openai import OpenAIEmbeddings

            load_env()
            self.embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
            self.faiss = FAISS.load_local(str(self.index_dir / FAISS_DIR), self.embeddings,
                                          allow_dangerous_deserialization=True)

    # ------------------------------------------------------------------ text access
    def raw_text(self, rel: str) -> Optional[str]:
        path = Path(self.meta["corpus_path"]) / rel
        if not path.exists() or path.suffix.lower() in {".pdf", ".docx"}:
            return None
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None

    def extracted(self, rel: str) -> Optional[str]:
        path = self.index_dir / EXTRACTED_DIR / (rel + ".txt")
        return path.read_text(encoding="utf-8") if path.exists() else None

    def visible_paths(self) -> set:
        return {d.metadata["path"] for d in self.visible}

    # ------------------------------------------------------------------ retrieval
    def retrievers(self) -> List:
        rets = [self.bm25]
        if self.faiss is not None:
            rets.append(self.faiss.as_retriever(search_kwargs={
                "k": RETRIEVE_K, "fetch_k": RETRIEVE_K * 4,
                "filter": lambda m: bool(m.get("customer_visible")),
            }))
        return rets

    def retrieve(self, question: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Fused candidates re-ranked by authority tier. Returns (doc, score) best first."""
        from langchain_classic.retrievers import EnsembleRetriever

        rets = self.retrievers()
        if len(rets) == 1:
            fused = rets[0].invoke(question)
        else:
            fused = EnsembleRetriever(retrievers=rets, weights=[0.4, 0.6]).invoke(question)
        scored: Dict[str, Tuple[Document, float]] = {}
        for rank, doc in enumerate(fused):
            cid = doc.metadata["chunk_id"]
            if cid in scored:
                continue
            base = 1.0 / (rank + 1)
            scored[cid] = (doc, base * weight_for_tier(int(doc.metadata.get("tier", 4))))
        ranked = sorted(scored.values(), key=lambda t: t[1], reverse=True)
        return ranked[:k]
