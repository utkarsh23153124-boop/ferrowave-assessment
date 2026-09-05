"""Hybrid retrieval: BM25 + FAISS fused by LangChain's EnsembleRetriever, then re-ranked
by authority tier from policy.py. Only customer-visible chunks are searched."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from .config import EMBED_MODEL, INDEX_DIR, RETRIEVE_K, TOP_K, load_env
from .ingest import CHUNKS_FILE, EXTRACTED_DIR, FAISS_DIR, META_FILE, header_for
from .policy import weight_for_tier
from .text import INJECTION_BLOCK, PROSE_SUFFIXES, normalize, tokenize


class Index:
    """Everything loaded from index/: chunks, metadata, BM25, FAISS (if built), and the
    normalised text of every visible document for quote verification (kept in memory so a
    concurrent reindex can never make verification read a half-written file)."""

    def __init__(self, index_dir: Path = INDEX_DIR, use_embeddings: Optional[bool] = None):
        self.index_dir = Path(index_dir)
        self.meta: Dict = json.loads((self.index_dir / META_FILE).read_text(encoding="utf-8"))
        self.docs: List[Document] = []
        with (self.index_dir / CHUNKS_FILE).open(encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                self.docs.append(Document(page_content=rec["text"], metadata=rec["metadata"]))
        self.visible = [d for d in self.docs if d.metadata.get("customer_visible")]
        if not self.visible:
            raise RuntimeError("index has no customer-visible chunks; rebuild from a corpus with public documents")
        self._visible_paths = frozenset(d.metadata["path"] for d in self.visible)
        self._haystacks = self._load_haystacks()

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
        self._retriever = self._build_retriever()

    # ------------------------------------------------------------------ text access
    def _load_haystacks(self) -> Dict[str, str]:
        """Normalised verification text per visible path. Prose formats (md, txt) verify
        against the raw file with injection blocks removed; everything else verifies against
        the loader's extracted text, since that is where the quotable rendering lives."""
        corpus = Path(self.meta["corpus_path"])
        out: Dict[str, str] = {}
        for rel in self._visible_paths:
            src = corpus / rel
            if src.suffix.lower() in PROSE_SUFFIXES and src.exists():
                try:
                    out[rel] = normalize(INJECTION_BLOCK.sub("", src.read_text(encoding="utf-8")))
                    continue
                except UnicodeDecodeError:
                    pass
            ext = self.index_dir / EXTRACTED_DIR / (rel + ".txt")
            if ext.exists():
                out[rel] = normalize(ext.read_text(encoding="utf-8"))
        return out

    def quote_in_file(self, rel: str, quote: str) -> bool:
        q = normalize(quote)
        if len(q) < 8:
            return False
        hay = self._haystacks.get(rel)
        return bool(hay) and q in hay

    def visible_paths(self) -> frozenset:
        return self._visible_paths

    # ------------------------------------------------------------------ retrieval
    def _build_retriever(self):
        if self.faiss is None:
            return self.bm25
        from langchain_classic.retrievers import EnsembleRetriever

        # The FAISS store only contains visible chunks, so no filter is needed here.
        dense = self.faiss.as_retriever(search_kwargs={"k": RETRIEVE_K})
        return EnsembleRetriever(retrievers=[self.bm25, dense], weights=[0.4, 0.6])

    def retrieve(self, question: str, k: int = TOP_K) -> List[Tuple[Document, float]]:
        """Fused candidates re-ranked by authority tier. Returns (doc, score) best first."""
        fused = self._retriever.invoke(question)
        scored = [
            (doc, weight_for_tier(int(doc.metadata.get("tier", 4))) / (rank + 1))
            for rank, doc in enumerate(fused)
            if doc.metadata.get("customer_visible")  # belt and braces; both retrievers are visible-only
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:k]
