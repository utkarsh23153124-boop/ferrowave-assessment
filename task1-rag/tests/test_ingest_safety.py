"""Ingest must never destroy a working index or delete a directory that is not an index."""
import os

import pytest

from rag.ingest import _looks_like_index, build_documents, decide_embed, write_index


def test_refuses_to_overwrite_a_non_index_directory(tmp_path, corpus):
    victim = tmp_path / "notanindex"
    victim.mkdir()
    (victim / "important.txt").write_text("keep me", encoding="utf-8")
    docs, extracted, report = build_documents(corpus)
    with pytest.raises(RuntimeError):
        write_index(docs, extracted, report, corpus, victim, embed=False)
    assert (victim / "important.txt").read_text(encoding="utf-8") == "keep me"


def test_failed_build_keeps_previous_index(tmp_path, corpus, monkeypatch):
    out = tmp_path / "index"
    docs, extracted, report = build_documents(corpus)
    write_index(docs, extracted, report, corpus, out, embed=False)
    marker = (out / "meta.json").read_text(encoding="utf-8")
    # Force the embedding step to fail: no key in the environment and embed=True.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("rag.ingest.load_env", lambda: None)
    with pytest.raises(Exception):
        write_index(docs, extracted, report, corpus, out, embed=True)
    assert (out / "meta.json").read_text(encoding="utf-8") == marker, "old index must survive a failed rebuild"
    assert not out.with_name("index.tmp").exists()


def test_decide_embed_degrades_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("rag.ingest.load_env", lambda: None)
    assert decide_embed(no_embed_flag=False) is False
    assert decide_embed(no_embed_flag=True) is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert decide_embed(no_embed_flag=False) is True


def test_looks_like_index(tmp_path):
    assert _looks_like_index(tmp_path / "missing")
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _looks_like_index(empty)
    (empty / "meta.json").write_text("{}", encoding="utf-8")
    assert _looks_like_index(empty)
    other = tmp_path / "other"
    other.mkdir()
    (other / "x.py").write_text("", encoding="utf-8")
    assert not _looks_like_index(other)
