"""Run the eval set against the service and write eval/results.md + eval/results.jsonl.

    python eval/run.py                              # POST to http://127.0.0.1:8000/ask
    python eval/run.py --url http://host:port/ask
    python eval/run.py --direct                     # in-process, no server needed

Grading per question:
  status   expected_status == got status              (required for pass)
  sources  any expected_sources path appears in citations (skipped when none expected)
  keywords every expected_keywords phrase appears in the answer, case-insensitive
  pass = all three; partial = status right but sources or keywords missed; fail = wrong status.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))


def ask_http(url: str, question: str) -> dict:
    import httpx

    r = httpx.post(url, json={"question": question}, timeout=120)
    r.raise_for_status()
    return r.json()


def grade(q: dict, res: dict) -> tuple[str, str]:
    status_ok = res["status"] == q["expected_status"]
    cited = {c["path"] for c in res.get("citations", [])}
    exp_sources = q.get("expected_sources") or []
    sources_ok = (not exp_sources) or bool(cited & set(exp_sources))
    answer = res.get("answer", "").lower()
    missing = [k for k in (q.get("expected_keywords") or []) if k.lower() not in answer]
    keywords_ok = not missing
    if not status_ok:
        return "fail", f"status {res['status']} != {q['expected_status']}"
    if sources_ok and keywords_ok:
        return "pass", "status, sources and keywords all matched"
    reasons = []
    if not sources_ok:
        reasons.append(f"cited {sorted(cited) or 'nothing'}, expected one of {exp_sources}")
    if not keywords_ok:
        reasons.append(f"answer missing {missing}")
    return "partial", "; ".join(reasons)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/ask")
    ap.add_argument("--direct", action="store_true", help="call the answerer in-process")
    ap.add_argument("--questions", default=str(HERE / "questions.jsonl"))
    ap.add_argument("--only", default="", help="comma-separated question ids")
    args = ap.parse_args()

    questions = [json.loads(l) for l in Path(args.questions).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        keep = set(args.only.split(","))
        questions = [q for q in questions if q["id"] in keep]

    if args.direct:
        from rag.answer import Answerer
        from rag.retrieve import Index

        answerer = Answerer(Index())
        ask = answerer.ask
    else:
        ask = lambda question: ask_http(args.url, question)  # noqa: E731

    rows = []
    for q in questions:
        t0 = time.perf_counter()
        try:
            res = ask(q["question"])
        except Exception as exc:
            res = {"answer": f"ERROR {exc}", "status": "error", "citations": [], "confidence": None,
                   "diagnostics": {"latency_ms": int((time.perf_counter() - t0) * 1000), "estimated_cost_usd": 0, "tokens_in": 0, "tokens_out": 0}}
        verdict, reason = grade(q, res)
        rows.append({"q": q, "res": res, "verdict": verdict, "reason": reason})
        print(f"{q['id']} {verdict:7s} [{res['status']}] {q['question'][:70]}")

    (HERE / "results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    lat = sorted(r["res"]["diagnostics"]["latency_ms"] for r in rows)
    cost = [r["res"]["diagnostics"].get("estimated_cost_usd", 0) for r in rows]
    p50 = statistics.median(lat) if lat else 0
    p95 = lat[max(0, int(round(0.95 * len(lat))) - 1)] if lat else 0
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in ("pass", "partial", "fail")}
    by_status: dict = {}
    for r in rows:
        s = r["q"]["expected_status"]
        by_status.setdefault(s, {"n": 0, "pass": 0, "partial": 0, "fail": 0})
        by_status[s]["n"] += 1
        by_status[s][r["verdict"]] += 1

    out = ["# Eval results", "",
           f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')} | questions: {len(rows)} | "
           f"pass {counts['pass']} / partial {counts['partial']} / fail {counts['fail']}", "",
           f"Latency ms: p50 {p50:.0f}, p95 {p95}, max {lat[-1] if lat else 0} | "
           f"cost per question: mean ${statistics.mean(cost):.5f}, total ${sum(cost):.4f}", "",
           "## By expected status", "", "| expected status | n | pass | partial | fail |", "|---|---|---|---|---|"]
    for s, c in by_status.items():
        out.append(f"| {s} | {c['n']} | {c['pass']} | {c['partial']} | {c['fail']} |")
    out += ["", "## Per question", ""]
    for r in rows:
        q, res = r["q"], r["res"]
        cites = "<br>".join(f"`{c['path']}`: \"{c['quote'][:120]}\"" for c in res.get("citations", [])) or "(none)"
        out += [f"### {q['id']} {r['verdict'].upper()}: {q['question']}", "",
                f"- expected: **{q['expected_status']}**, {q.get('expected_answer', '')}",
                f"- got: **{res['status']}** (confidence {res.get('confidence')}, {res['diagnostics']['latency_ms']} ms)",
                f"- answer: {res['answer']}",
                f"- citations: {cites}",
                f"- judgement: {r['reason']}",
                f"- why this question: {q.get('notes', '')}", ""]
    (HERE / "results.md").write_text("\n".join(out), encoding="utf-8")
    print(f"\npass {counts['pass']} / partial {counts['partial']} / fail {counts['fail']} of {len(rows)} | p50 {p50:.0f} ms, p95 {p95} ms | mean cost ${statistics.mean(cost):.5f}")
    print(f"wrote {HERE / 'results.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
