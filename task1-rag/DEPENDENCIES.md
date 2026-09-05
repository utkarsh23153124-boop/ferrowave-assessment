# DEPENDENCIES.md

Task: Task 1 (answer engine)

Every third-party package beyond the Python 3.12 standard library. Versions are what is
pinned or installed on the build machine.

| Package | Version | What it does for me here | What I would have to write if it were removed | Risk (size, maintenance, licence, lock-in) |
|---|---|---|---|---|
| `langchain-core` | 1.2.23 | `Document` type and the message / runnable primitives the rest of LangChain builds on. | A small dataclass for chunks plus dicts for messages. | MIT. Large surface, frequent releases; pinned to `>=1.2,<2`. |
| `langchain-community` | 0.4.1 | `BM25Retriever` and the `FAISS` vector store wrapper (save, load, filtered search). | About 60 lines: a BM25 wrapper over `rank_bm25` and a FAISS index with a parallel metadata list. | MIT. Lazy imports mean import errors surface late. Contains far more than I use. |
| `langchain-classic` | 1.0.3 | `EnsembleRetriever`: reciprocal rank fusion of BM25 and FAISS results. | 15 lines of RRF. This is the smallest piece of value in the stack; it is here because the framework choice was explicit. | MIT. "Classic" signals it is the legacy home for this class; may move again. |
| `langchain-openai` | 1.6.0 | `ChatOpenAI.with_structured_output` (pydantic schema in, parsed object plus raw usage out) and `OpenAIEmbeddings`. | Direct calls with the `openai` client using `response_format` JSON schema and manual parsing; roughly 40 lines. | MIT. Tracks OpenAI API changes; version pinned. |
| `langchain-text-splitters` | 1.1.1 | `MarkdownHeaderTextSplitter` (keeps heading breadcrumbs) and `RecursiveCharacterTextSplitter` for long sections. | A heading-aware splitter, about 50 lines; the recursive splitter is 20 more. | MIT. Small, stable. |
| `openai` | 3.7.0 | The HTTP client underneath `langchain-openai`; also used directly in the key smoke test. | `httpx` calls to two endpoints. | Apache 2.0. Vendor lock-in is in the model choice, not the client. |
| `faiss-cpu` | 1.13.2 | Exact inner-product search over 276 vectors. Honestly oversized for this corpus. | `numpy` dot product over a 276 x 1536 matrix; five lines. Kept because it is the LangChain vector store that supports a metadata filter callable and save/load without a server. | MIT. Binary wheel, 30 MB. No maintenance risk from Meta, but heavy for what it does. |
| `rank_bm25` | 0.2.2 | BM25Okapi scoring used by `BM25Retriever`. | The BM25 formula, 40 lines. | Apache 2.0. Tiny, unmaintained since 2022, but the algorithm does not change. |
| `beautifulsoup4` | 4.12.3 | HTML parsing for the two HTML files: tables with colspan, definition lists, stripping nav and style. | `html.parser` from the standard library with a hand-rolled tree walk; painful for colspan. | MIT. Very stable. |
| `lxml` | 5.2.2 | Fast, lenient parser backend for BeautifulSoup. | Use the built-in `html.parser` backend (slower, slightly different whitespace). | BSD. C extension, binary wheel. |
| `pypdf` | 6.10.2 | Text extraction from the Terms of Service PDF. | Not realistically; PDF text extraction is not a weekend project. | BSD. Pure Python, active. Extraction quality depends on the PDF; this one is clean. |
| `python-docx` | 1.2.0 | Reads the DPA: paragraphs with style names and the sub-processor table, in document order. | Unzip the docx and walk `word/document.xml` with `xml.etree`; about 80 lines. | MIT. Stable. |
| `fastapi` | 0.115.0 | The `/ask`, `/health`, `/reindex` endpoints with request validation. | `http.server` plus manual JSON validation; or Flask. | MIT. Depends on Starlette and pydantic; both pinned transitively. |
| `uvicorn` | 0.30.6 | ASGI server for FastAPI. | Any ASGI server; or `wsgiref` with a WSGI framework. | BSD. |
| `pydantic` | 2.9.2 | Request schemas and the structured-output `Draft` schema the model must fill. | Dataclasses plus manual validation; the structured output contract would need a hand-written JSON schema. | MIT. Already required by FastAPI and LangChain. |
| `httpx` | 0.27.2 | HTTP client in `eval/run.py` to post to the running service. | `urllib.request`. | BSD. Already a transitive dependency of `openai`. |
| `pytest` | 9.1.1 | Test runner for the 17 offline tests. | `unittest`. | MIT. Dev only. |

## Framework accounting

What LangChain is doing for me that I can name: the `Document` container, header-aware
Markdown splitting, structured output with usage metadata in one call, FAISS save/load
with a metadata filter, and rank fusion. What it is not doing: loaders (all custom, because
the generic ones lose the table in the DPA and the colspan in the rate-limit page),
precedence, visibility, the plan gate, citation verification, and the fallback citation.
Those are the parts that decide whether the system is trustworthy, and they are plain
Python in `rag/policy.py` and `rag/answer.py`. If LangChain were removed, the retrieval and
generation code would be roughly 150 lines longer and the guardrails would be unchanged.
