"""Build the index from a corpus directory.

    python ingest.py --corpus ../corpus            # full build (embeds if OPENAI_API_KEY is set)
    python ingest.py --corpus ../corpus --no-embed  # BM25-only index, no network

The manifest is the ingestion allowlist: a file that is not in _manifest.csv is not
indexed. Every chunk carries the manifest row (audience, status, dates, notes) plus the
authority tier and visibility decision from policy.py, so retrieval can filter and rank
without re-reading the manifest.

The index is built into a temporary directory and swapped into place only when complete,
so a failed build (no key, network error) never destroys the working index.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from langchain_core.documents import Document

from .config import DEFAULT_CORPUS, EMBED_MODEL, INDEX_DIR, MANIFEST_NAME, load_env
from .loaders import extracted_text, load_file
from .policy import customer_visible, folder_of, is_stale, tier_for

CHUNKS_FILE = "chunks.jsonl"
META_FILE = "meta.json"
EXTRACTED_DIR = "extracted"
FAISS_DIR = "faiss"
_INDEX_MARKERS = {CHUNKS_FILE, META_FILE, EXTRACTED_DIR, FAISS_DIR}


def read_manifest(corpus: Path) -> List[Dict[str, str]]:
    path = corpus / MANIFEST_NAME
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("path") or "").strip()]
    for r in rows:
        for k, v in list(r.items()):
            r[k] = (v or "").strip()
    # Reverse the `supersedes` column: a document named as superseded by another row is
    # hidden even if its own status column was not updated.
    superseded_by = {r["supersedes"]: r["path"] for r in rows if r.get("supersedes")}
    for r in rows:
        r["_superseded_by"] = superseded_by.get(r["path"], "")
    return rows


def header_for(doc: Document) -> str:
    """Text used for embedding and BM25: title and section give short chunks context."""
    m = doc.metadata
    return f"{m.get('title', '')} > {m.get('section', '')}\n{doc.page_content}"


def build_documents(corpus: Path) -> Tuple[List[Document], Dict[str, str], List[Dict]]:
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
        stale = is_stale(row.get("last_updated", ""))
        for i, (section, text, extra) in enumerate(pieces):
            meta = {
                "path": rel,
                "title": row.get("title", rel),
                "audience": row.get("audience", ""),
                "status": row.get("status", ""),
                "last_updated": row.get("last_updated", ""),
                "supersedes": row.get("supersedes", ""),
                "superseded_by": row.get("_superseded_by", ""),
                "notes": row.get("notes", ""),
                "folder": folder_of(rel),
                "tier": tier,
                "stale": stale,
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


def _looks_like_index(path: Path) -> bool:
    """Refuse to delete a directory that is not one of ours (guards --index ../corpus)."""
    if not path.exists():
        return True
    names = {p.name for p in path.iterdir()}
    return not names or bool(names & _INDEX_MARKERS)


def write_index(docs: List[Document], extracted: Dict[str, str], report: List[Dict],
                corpus: Path, index_dir: Path, embed: bool) -> Dict:
    index_dir = Path(index_dir)
    if not _looks_like_index(index_dir):
        raise RuntimeError(f"refusing to overwrite {index_dir}: it does not look like an index directory")
    tmp = index_dir.with_name(index_dir.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        meta = _write_into(docs, extracted, report, corpus, tmp, embed)
        if index_dir.exists():
            shutil.rmtree(index_dir)
        os.replace(tmp, index_dir)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return meta


def _write_into(docs: List[Document], extracted: Dict[str, str], report: List[Dict],
                corpus: Path, out: Path, embed: bool) -> Dict:
    with (out / CHUNKS_FILE).open("w", encoding="utf-8") as fh:
        for d in docs:
            fh.write(json.dumps({"text": d.page_content, "metadata": d.metadata}, ensure_ascii=False) + "\n")
    ext_dir = out / EXTRACTED_DIR
    for rel, text in extracted.items():
        target = ext_dir / (rel + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    embed_tokens = 0
    embed_seconds = 0.0
    if embed:
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
        # Only customer-visible chunks are embedded: hidden ones can never be returned, so
        # embedding them costs money and candidate slots for nothing.
        emb_docs = [d for d in docs if d.metadata["customer_visible"]]
        texts = [header_for(d) for d in emb_docs]
        t0 = time.perf_counter()
        vectors = embeddings.embed_documents(texts)
        embed_seconds = time.perf_counter() - t0
        embed_tokens = sum(len(t) // 4 for t in texts)  # estimate; the embeddings API does not return usage here
        store = FAISS.from_embeddings(
            text_embeddings=list(zip([d.page_content for d in emb_docs], vectors)),
            embedding=embeddings,
            metadatas=[d.metadata for d in emb_docs],
        )
        store.save_local(str(out / FAISS_DIR))

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
    (out / META_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def decide_embed(no_embed_flag: bool) -> bool:
    """Embed only when asked to and a key is available; say so when degrading."""
    if no_embed_flag:
        return False
    load_env()
    if not os.getenv("OPENAI_API_KEY"):
        print("WARN OPENAI_API_KEY not set; building a BM25-only index (no embeddings)", file=sys.stderr)
        return False
    return True


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
    if not any(d.metadata["customer_visible"] for d in docs):
        print("No customer-visible documents in this corpus; refusing to build an empty index.", file=sys.stderr)
        return 1
    meta = write_index(docs, extracted, report, corpus, Path(args.index), embed=decide_embed(args.no_embed))
    hidden = [r for r in report if r.get("visible") is False]
    errors = [r for r in report if r.get("error")]
    print(f"Indexed {meta['documents']} documents / {meta['chunks']} chunks into {args.index}")
    print(f"  customer-visible: {meta['documents_customer_visible']} documents / {meta['chunks_customer_visible']} chunks")
    print(f"  hidden from customers: {', '.join(r['path'] + ' (' + r['why'] + ')' for r in hidden) or 'none'}")
    if errors:
        print(f"  errors: {errors}")
    print(f"  embeddings: {'yes, ' + str(meta['embed_model']) if meta['embedded'] else 'skipped (BM25 only)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
