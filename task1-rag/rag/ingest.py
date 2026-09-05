"""Build the index from a corpus directory.

    python ingest.py --corpus ../corpus            # full build (needs OPENAI_API_KEY)
    python ingest.py --corpus ../corpus --no-embed  # BM25-only index, no network

The manifest is the ingestion allowlist: a file that is not in _manifest.csv is not
indexed. Every chunk carries the manifest row (audience, status, dates, notes) plus the
authority tier and visibility decision from policy.py, so retrieval can filter and rank
without re-reading the manifest.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from langchain_core.documents import Document

from .config import DEFAULT_CORPUS, EMBED_MODEL, INDEX_DIR, MANIFEST_NAME, load_env
from .loaders import extracted_text, load_file
from .policy import customer_visible, folder_of, tier_for

CHUNKS_FILE = "chunks.jsonl"
META_FILE = "meta.json"
EXTRACTED_DIR = "extracted"
FAISS_DIR = "faiss"


def read_manifest(corpus: Path) -> List[Dict[str, str]]:
    path = corpus / MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("path") or "").strip()]
    for r in rows:
        for k, v in list(r.items()):
            r[k] = (v or "").strip()
    return rows


def header_for(doc: Document) -> str:
    """Text used for embedding and BM25: title and section give short chunks context."""
    m = doc.metadata
    return f"{m.get('title', '')} > {m.get('section', '')}\n{doc.page_content}"


def build_documents(corpus: Path) -> tuple[List[Document], Dict[str, str], List[Dict]]:
    docs: List[Document] = []
    extracted: Dict[str, str] = {}
    report: List[Dict] = []
    for row in read_manifest(corpus):
        rel = row["path"]
        file_path = corpus / rel
        if not file_path.exists():
            report.append({"path": rel, "error": "missing on disk"})
            print(f"WARN missing file listed in manifest: {rel}", file=sys.stderr)
            continue
        try:
            pieces = load_file(file_path, rel)
        except Exception as exc:  # keep going; report it
            report.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})
            print(f"WARN failed to load {rel}: {exc}", file=sys.stderr)
            continue
        visible, why = customer_visible(row)
        tier = tier_for(row)
        for i, (section, text, extra) in enumerate(pieces):
            meta = {
                "path": rel,
                "title": row.get("title", rel),
                "audience": row.get("audience", ""),
                "status": row.get("status", ""),
                "last_updated": row.get("last_updated", ""),
                "supersedes": row.get("supersedes", ""),
                "notes": row.get("notes", ""),
                "folder": folder_of(rel),
                "tier": tier,
                "customer_visible": visible,
                "visibility_reason": why,
                "section": section,
                "chunk_id": f"{rel}#{i}",
            }
            meta.update(extra)
            docs.append(Document(page_content=text, metadata=meta))
        extracted[rel] = extracted_text(pieces)
        report.append({"path": rel, "chunks": len(pieces), "tier": tier, "visible": visible, "why": why})
    return docs, extracted, report


def write_index(docs: List[Document], extracted: Dict[str, str], report: List[Dict],
                corpus: Path, index_dir: Path, embed: bool) -> Dict:
    if index_dir.exists():
        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True)
    with (index_dir / CHUNKS_FILE).open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps({"text": d.page_content, "metadata": d.metadata}, ensure_ascii=False) + "\n")
    ext_dir = index_dir / EXTRACTED_DIR
    for rel, text in extracted.items():
        out = ext_dir / (rel + ".txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")

    embed_tokens = 0
    embed_seconds = 0.0
    if embed:
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings

        load_env()
        embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
        texts = [header_for(d) for d in docs]
        t0 = time.perf_counter()
        vectors = embeddings.embed_documents(texts)
        embed_seconds = time.perf_counter() - t0
        embed_tokens = sum(len(t) // 4 for t in texts)  # estimate; the embeddings API does not return usage here
        store = FAISS.from_embeddings(
            text_embeddings=list(zip([d.page_content for d in docs], vectors)),
            embedding=embeddings,
            metadatas=[d.metadata for d in docs],
        )
        store.save_local(str(index_dir / FAISS_DIR))

    visible_paths = {d.metadata["path"] for d in docs if d.metadata["customer_visible"]}
    all_paths = {d.metadata["path"] for d in docs}
    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "corpus_path": str(corpus.resolve()),
        "documents": len(all_paths),
        "documents_customer_visible": len(visible_paths),
        "chunks": len(docs),
        "chunks_customer_visible": sum(1 for d in docs if d.metadata["customer_visible"]),
        "embedded": embed,
        "embed_model": EMBED_MODEL if embed else None,
        "embed_tokens_estimate": embed_tokens,
        "embed_seconds": round(embed_seconds, 2),
        "files": report,
    }
    (index_dir / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rebuild the Task 1 index from a corpus directory.")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS), help="directory containing _manifest.csv")
    ap.add_argument("--index", default=str(INDEX_DIR), help="output index directory")
    ap.add_argument("--no-embed", action="store_true", help="skip embeddings (BM25-only index, no network)")
    args = ap.parse_args(argv)
    corpus = Path(args.corpus)
    docs, extracted, report = build_documents(corpus)
    if not docs:
        print("No documents loaded; nothing written.", file=sys.stderr)
        return 1
    meta = write_index(docs, extracted, report, corpus, Path(args.index), embed=not args.no_embed)
    hidden = [r for r in report if r.get("visible") is False]
    errors = [r for r in report if r.get("error")]
    print(f"Indexed {meta['documents']} documents / {meta['chunks']} chunks into {args.index}")
    print(f"  customer-visible: {meta['documents_customer_visible']} documents / {meta['chunks_customer_visible']} chunks")
    print(f"  hidden from customers: {', '.join(r['path'] + ' (' + r['why'] + ')' for r in hidden) or 'none'}")
    if errors:
        print(f"  errors: {errors}")
    print(f"  embeddings: {'yes, ' + str(meta['embed_model']) : <40}" if meta["embedded"] else "  embeddings: skipped (--no-embed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
