import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.config import DEFAULT_CORPUS  # noqa: E402
from rag.ingest import build_documents, write_index  # noqa: E402
from rag.retrieve import Index  # noqa: E402

CORPUS = DEFAULT_CORPUS


@pytest.fixture(scope="session")
def corpus() -> Path:
    assert (CORPUS / "_manifest.csv").exists(), f"corpus not found at {CORPUS}"
    return CORPUS


@pytest.fixture(scope="session")
def offline_index(tmp_path_factory, corpus) -> Index:
    """A BM25-only index built into a temp dir. No network, no API key."""
    out = tmp_path_factory.mktemp("index")
    docs, extracted, report = build_documents(corpus)
    write_index(docs, extracted, report, corpus, out, embed=False)
    return Index(out, use_embeddings=False)
