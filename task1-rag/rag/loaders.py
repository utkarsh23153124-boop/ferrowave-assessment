"""Per-format loaders. Each returns a list of (section, text, extra_metadata) tuples.

Every loader exists because the generic one would lose or mangle something specific in
this corpus. See CORPUS_NOTES.md for the traps each one handles.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from bs4 import BeautifulSoup, NavigableString, Tag
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from .config import CHUNK_OVERLAP, CHUNK_SIZE
from .policy import STAFF_AUTHOR_RE
from .text import INJECTION_BLOCK

Piece = Tuple[str, str, Dict[str, Any]]  # (section, text, extra metadata)
_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def _split_long(section: str, text: str, extra: Dict[str, Any]) -> List[Piece]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [(section, text, dict(extra))]
    return [(section, part, dict(extra)) for part in _splitter.split_text(text)]


# ----------------------------------------------------------------------------- markdown
_POST_HEADER = re.compile(r"^\*\*(?P<author>[^*]+)\*\*\s*\((?P<date>[^)]+)\)\s*$", re.M)


def load_markdown(path: Path, rel: str) -> List[Piece]:
    raw = path.read_text(encoding="utf-8")
    if rel.startswith("community/"):
        return _load_forum(raw)
    headers = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")], strip_headers=False
    )
    pieces: List[Piece] = []
    for doc in headers.split_text(raw):
        crumbs = [doc.metadata.get(k) for k in ("h2", "h3") if doc.metadata.get(k)]
        section = " > ".join(crumbs) if crumbs else (doc.metadata.get("h1") or "")
        pieces.extend(_split_long(section, doc.page_content, {}))
    return pieces


def _load_forum(raw: str) -> List[Piece]:
    """Forum threads: one chunk per post, injection blocks stripped, staff posts flagged."""
    pieces: List[Piece] = []
    blocks = [b.strip() for b in re.split(r"^---\s*$", raw, flags=re.M)]
    intro = blocks[0] if blocks else ""
    title = intro.splitlines()[0].lstrip("# ").strip() if intro else "thread"
    for block in blocks[1:]:
        if not block:
            continue
        m = _POST_HEADER.search(block)
        if not m:
            continue
        author, posted = m.group("author").strip(), m.group("date").strip()
        body = block[m.end():].strip()
        stripped = INJECTION_BLOCK.sub("", body)
        injected = stripped != body
        body = re.sub(r"\n{3,}", "\n\n", stripped).strip()
        role = "staff" if STAFF_AUTHOR_RE.search(author) else "user"
        text = f"Forum thread: {title}\nPost by {author} ({role}), {posted}:\n{body}"
        pieces.append((f"post by {author} ({posted})", text, {
            "author": author, "author_role": role, "injection_stripped": injected,
        }))
    return pieces


# --------------------------------------------------------------------------------- html
def _cell_texts(row: Tag) -> List[str]:
    out: List[str] = []
    for cell in row.find_all(["td", "th"], recursive=False):
        txt = " ".join(cell.get_text(" ", strip=True).split())
        span = int(cell.get("colspan", 1) or 1)
        out.extend([txt] * span)
    return out


def _render_table(table: Tag) -> str:
    header: List[str] = []
    thead = table.find("thead")
    if thead and thead.find("tr"):
        header = _cell_texts(thead.find("tr"))
    lines: List[str] = []
    body = table.find("tbody") or table
    for tr in body.find_all("tr", recursive=True):
        if thead is not None and tr.find_parent("thead") is thead:
            continue
        if tr.find_parent("tfoot") is not None:
            continue
        cells = _cell_texts(tr)
        if not header:
            header = cells
            continue
        lines.append(" | ".join(f"{h}: {c}" for h, c in zip(header, cells)))
    tfoot = table.find("tfoot")
    if tfoot is not None:
        for tr in tfoot.find_all("tr"):
            note = " ".join(tr.get_text(" ", strip=True).split())
            if note:
                lines.append(f"Note: {note}")
    return "\n".join(lines)


def load_html(path: Path, rel: str) -> List[Piece]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    for junk in soup.find_all(["nav", "style", "script", "head"]):
        junk.decompose()
    body = soup.body or soup
    pieces: List[Piece] = []
    section = ""
    buffer: List[str] = []

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        if text:
            pieces.extend(_split_long(section, text, {}))
        buffer = []

    for el in body.children:
        if isinstance(el, NavigableString):
            continue
        name = el.name
        if name in ("h1", "h2", "h3"):
            flush()
            section = " ".join(el.get_text(" ", strip=True).split())
            buffer.append(section)
        elif name == "table":
            flush()
            pieces.append((section, f"{section}\n{_render_table(el)}".strip(), {"kind": "table"}))
        elif name == "dl":
            flush()
            for dt in el.find_all("dt"):
                dd = dt.find_next_sibling("dd")
                q = " ".join(dt.get_text(" ", strip=True).split())
                a = " ".join(dd.get_text(" ", strip=True).split()) if dd else ""
                pieces.append((f"{section} > {q}", f"Q: {q}\nA: {a}", {"kind": "faq"}))
        elif name in ("ul", "ol"):
            buffer.extend("- " + " ".join(li.get_text(" ", strip=True).split()) for li in el.find_all("li"))
        else:
            txt = " ".join(el.get_text(" ", strip=True).split())
            if txt:
                buffer.append(txt)
    flush()
    return pieces


# ---------------------------------------------------------------------------------- csv
def load_csv(path: Path, rel: str) -> List[Piece]:
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))
    if not rows:
        return []
    pieces: List[Piece] = []
    key = list(rows[0].keys())[0]
    overview = [f"{r[key]} (minimum plan {r.get('minimum_plan', '?')}, status {r.get('status', '?')})" for r in rows]
    pieces.append(("overview", "Integrations directory. Available integrations: " + "; ".join(overview) + ".", {"kind": "table"}))
    for r in rows:
        text = "\n".join(f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in r.items())
        pieces.append((r[key], text, {"kind": "row"}))
    return pieces


# --------------------------------------------------------------------------------- json
def _money(minor: Any, currency: str = "USD") -> str:
    if minor is None:
        return "not offered"
    try:
        return f"{currency} {int(minor) / 100:,.2f}"
    except (TypeError, ValueError):
        return str(minor)


_KNOWN_PLAN_KEYS = {
    "id", "name", "monthly_usd_minor", "annual_usd_minor", "monthly_eur_minor", "annual_eur_minor",
    "seats_included", "extra_seat_monthly_usd_minor", "responses_per_month", "overage_behaviour",
    "overage_per_1000_usd_minor", "features", "sso", "scim", "webhooks", "api", "pulse_alerts",
    "eu_residency", "pulse_signals", "webhook_log_retention_days", "pricing", "contract",
}


def _plan_prose(plan: Dict[str, Any]) -> str:
    """Render one plan object as prose. Minor units become money; null means 'not offered'."""
    name = plan.get("name", plan.get("id", "plan"))
    lines = [f"{name} plan (plan id: {plan.get('id')})."]
    if plan.get("monthly_usd_minor") is not None:
        price = f"Price: {_money(plan['monthly_usd_minor'])} per month or {_money(plan.get('annual_usd_minor'))} per year"
        if plan.get("monthly_eur_minor") is not None:
            price += f"; {_money(plan['monthly_eur_minor'], 'EUR')} per month or {_money(plan.get('annual_eur_minor'), 'EUR')} per year (EUR excludes VAT)"
        lines.append(price + ".")
    else:
        lines.append("Price: custom, quoted by sales (no published monthly or annual price).")
    if plan.get("contract"):
        lines.append(f"Contract: {str(plan['contract']).replace('_', ' ')}.")
    lines.append(f"Seats included: {plan.get('seats_included')}.")
    if "extra_seat_monthly_usd_minor" in plan:
        extra = plan["extra_seat_monthly_usd_minor"]
        lines.append("Extra seats: " + ("not offered" if extra is None else _money(extra) + " per seat per month") + ".")
    resp = plan.get("responses_per_month")
    lines.append(f"Responses per month: {resp:,}." if isinstance(resp, int) else f"Responses per month: {str(resp).replace('_', ' ')}.")
    beh = plan.get("overage_behaviour")
    if beh:
        human = {"pause_collection": "collection pauses until the next cycle", "bill_overage": "overage is billed"}.get(beh, beh.replace("_", " "))
        lines.append(f"When the monthly allowance is reached: {human}.")
    if "overage_per_1000_usd_minor" in plan:
        ov = plan["overage_per_1000_usd_minor"]
        lines.append("Overage rate: " + ("not offered" if ov is None else _money(ov) + " per 1,000 responses") + ".")
    feats = plan.get("features") or []
    if feats:
        lines.append("Features: " + ", ".join(str(f).replace("_", " ") for f in feats) + ".")
    for key, label in (("sso", "SAML SSO"), ("scim", "SCIM provisioning"), ("webhooks", "Webhooks"),
                       ("api", "API access"), ("pulse_alerts", "Pulse Alerts"), ("eu_residency", "EU data residency")):
        if key in plan:
            lines.append(f"{label}: {'yes' if plan[key] else 'no'}.")
    sig = plan.get("pulse_signals")
    if sig is not None:
        m = re.match(r"addon_(\d+)_usd_minor_monthly", str(sig))
        human = f"available as an add-on at {_money(int(m.group(1)))} per month" if m else str(sig).replace("_", " ")
        lines.append(f"Pulse Signals: {human}.")
    if "webhook_log_retention_days" in plan:
        lines.append(f"Webhook delivery log retention: {plan['webhook_log_retention_days']} days.")
    for k, v in plan.items():
        if k not in _KNOWN_PLAN_KEYS:
            lines.append(f"{k.replace('_', ' ').capitalize()}: {v}.")
    return "\n".join(lines)


def load_json(path: Path, rel: str) -> List[Piece]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pieces: List[Piece] = []
    top = {k: v for k, v in data.items() if not isinstance(v, (list, dict))}
    if top:
        pieces.append(("about", "Plan matrix. " + " ".join(f"{k.replace('_', ' ')}: {v}." for k, v in top.items()), {"kind": "json"}))
    for plan in data.get("plans", []):
        pieces.append((plan.get("name", plan.get("id", "plan")), _plan_prose(plan), {"kind": "json"}))
    return pieces


# ---------------------------------------------------------------------------------- pdf
_SECTION_HEAD = re.compile(r"^(\d{1,2}\. [A-Z][^\n]{2,60})$", re.M)
_CLAUSE = re.compile(r"(?<![\d.])(?=\d{1,2}\.\d{1,2} [A-Z\"'(])")


def load_pdf(path: Path, rel: str) -> List[Piece]:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    text = re.sub(r"[ \t]+\n", "\n", text)
    parts = _SECTION_HEAD.split(text)
    pieces: List[Piece] = []
    preamble = parts[0].strip()
    if preamble:
        pieces.extend(_split_long("preamble", preamble, {"kind": "pdf"}))
    for i in range(1, len(parts), 2):
        heading = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        body = " ".join(body.split())
        clauses = [c.strip() for c in _CLAUSE.split(body) if c.strip()]
        pieces.extend(_split_long(heading, heading + "\n" + "\n".join(clauses), {"kind": "pdf"}))
    return pieces


# --------------------------------------------------------------------------------- docx
def load_docx(path: Path, rel: str) -> List[Piece]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    pieces: List[Piece] = []
    section = "preamble"
    buffer: List[str] = []

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        if text:
            pieces.extend(_split_long(section, text, {"kind": "docx"}))
        buffer = []

    # Walk body children in document order so tables land under the heading they follow.
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            style = (para.style.name or "") if para.style is not None else ""
            txt = para.text.strip()
            if not txt:
                continue
            if style.startswith("Heading") or style == "Title":
                flush()
                section = txt
                buffer.append(txt)
            elif style.startswith("List"):
                buffer.append("- " + txt)
            else:
                buffer.append(txt)
        elif tag == "tbl":
            table = Table(child, document)
            rows = [[c.text.strip() for c in r.cells] for r in table.rows]
            if rows:
                header, body = rows[0], rows[1:]
                for r in body:
                    buffer.append("; ".join(f"{h}: {v}" for h, v in zip(header, r)))
    flush()
    return pieces


# ---------------------------------------------------------------------------------- txt
_RULE = re.compile(r"^-{20,}\s*$", re.M)


def load_txt(path: Path, rel: str) -> List[Piece]:
    raw = path.read_text(encoding="utf-8")
    parts = _RULE.split(raw)
    pieces: List[Piece] = []
    head = parts[0].strip()
    if head:
        pieces.append(("header", head, {"kind": "txt"}))
    # After splitting on the dash rules the pattern is: title, body, title, body ...
    i = 1
    while i < len(parts):
        title = parts[i].strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        i += 2
        if title and body:
            pieces.extend(_split_long(title, f"{title}\n{body}", {"kind": "txt"}))
    return pieces


LOADERS = {
    ".md": load_markdown,
    ".html": load_html,
    ".htm": load_html,
    ".csv": load_csv,
    ".json": load_json,
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".txt": load_txt,
}


def load_file(path: Path, rel: str) -> List[Piece]:
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        raise ValueError(f"No loader for {rel}")
    return loader(path, rel)


def extracted_text(pieces: List[Piece]) -> str:
    """Concatenated chunk text for a file; used to verify quotes from non-prose formats."""
    return "\n\n".join(p[1] for p in pieces)
