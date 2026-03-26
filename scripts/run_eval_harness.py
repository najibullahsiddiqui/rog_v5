from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app


DEFAULT_TEST_SET = Path("app/evals/default_test_set.json")
DEFAULT_REPORT_DIR = Path("data/eval_reports")


@dataclass
class EvalCaseResult:
    case_id: str
    category: str
    status: str
    latency_ms: float
    exact_match_success: bool
    grounded_success: bool
    unresolved: bool
    wrong_citation: bool
    answer_source: str
    notes: str


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _contains_all(haystack: str, needles: list[str]) -> bool:
    h = _normalize(haystack)
    return all(_normalize(n) in h for n in needles)


def _check_wrong_citation(
    citations: list[dict[str, Any]],
    expected_terms: list[str] | None,
    grounded_expected: bool,
) -> bool:
    if not grounded_expected:
        return False
    if not citations:
        return True
    if expected_terms:
        combined = " ".join(
            f"{c.get('excerpt', '')} {c.get('source', '')} {c.get('source_name', '')} {c.get('file_name', '')}"
            for c in citations
            if isinstance(c, dict)
        )
        return not _contains_all(combined, expected_terms)
    # minimal structural check
    for c in citations:
        if not isinstance(c, dict):
            return True
        if not any(c.get(k) for k in ("excerpt", "source", "source_name", "file_name", "doc_key")):
            return True
    return False


def run_eval(test_set_path: Path) -> dict[str, Any]:
    payload = json.loads(test_set_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    client = TestClient(app)

    results: list[EvalCaseResult] = []
    response_mode_distribution: dict[str, int] = {}

    for i, case in enumerate(cases):
        case_id = str(case.get("id") or f"case_{i+1}")
        category = str(case.get("type") or "unknown")
        query = str(case.get("query") or "").strip()
        session_key = str(case.get("session_key") or f"eval_{case_id}")
        if not query:
            results.append(
                EvalCaseResult(
                    case_id=case_id,
                    category=category,
                    status="skipped",
                    latency_ms=0.0,
                    exact_match_success=False,
                    grounded_success=False,
                    unresolved=False,
                    wrong_citation=False,
                    answer_source="",
                    notes="missing query",
                )
            )
            continue

        start = time.perf_counter()
        res = client.post("/api/ask", json={"question": query, "session_key": session_key})
        latency_ms = (time.perf_counter() - start) * 1000.0

        if res.status_code != 200:
            results.append(
                EvalCaseResult(
                    case_id=case_id,
                    category=category,
                    status="error",
                    latency_ms=latency_ms,
                    exact_match_success=False,
                    grounded_success=False,
                    unresolved=False,
                    wrong_citation=False,
                    answer_source="",
                    notes=f"http {res.status_code}",
                )
            )
            continue

        body = res.json()
        answer = str(body.get("answer") or "")
        grounded = bool(body.get("grounded"))
        unresolved = bool(body.get("unresolved_query_id")) or str(body.get("answer_source") or "") == "unresolved"
        citations = body.get("citations") or []
        answer_source = str(body.get("answer_source") or "unknown")

        response_mode_distribution[answer_source] = response_mode_distribution.get(answer_source, 0) + 1

        expected_answer_contains = case.get("expected_answer_contains") or []
        if isinstance(expected_answer_contains, str):
            expected_answer_contains = [expected_answer_contains]

        exact_match_success = _contains_all(answer, [str(x) for x in expected_answer_contains]) if expected_answer_contains else False

        expected_grounded = bool(case.get("expected_grounded", False))
        grounded_success = (grounded and bool(citations)) if expected_grounded else (not grounded or unresolved)

        wrong_citation = _check_wrong_citation(
            citations=citations,
            expected_terms=[str(x) for x in case.get("expected_citation_contains", [])],
            grounded_expected=expected_grounded,
        )

        notes: list[str] = []
        expected_mode = case.get("expected_answer_source")
        if expected_mode and answer_source != expected_mode:
            notes.append(f"expected source={expected_mode}, got={answer_source}")

        if category in {"decision_tree", "category_routing"} and expected_mode and answer_source != expected_mode:
            notes.append("routing mismatch")

        results.append(
            EvalCaseResult(
                case_id=case_id,
                category=category,
                status="ok",
                latency_ms=latency_ms,
                exact_match_success=exact_match_success,
                grounded_success=grounded_success,
                unresolved=unresolved,
                wrong_citation=wrong_citation,
                answer_source=answer_source,
                notes="; ".join(notes),
            )
        )

    ok_results = [r for r in results if r.status == "ok"]
    n = len(ok_results) or 1

    summary = {
        "total_cases": len(results),
        "ok_cases": len(ok_results),
        "exact_match_success": round(sum(1 for r in ok_results if r.exact_match_success) / n, 4),
        "grounded_answer_success": round(sum(1 for r in ok_results if r.grounded_success) / n, 4),
        "unresolved_rate": round(sum(1 for r in ok_results if r.unresolved) / n, 4),
        "wrong_citation_rate": round(sum(1 for r in ok_results if r.wrong_citation) / n, 4),
        "response_mode_distribution": response_mode_distribution,
        "latency_ms": {
            "avg": round(statistics.mean([r.latency_ms for r in ok_results]), 2) if ok_results else 0.0,
            "p95": round(sorted([r.latency_ms for r in ok_results])[max(0, int(0.95 * len(ok_results)) - 1)], 2)
            if ok_results
            else 0.0,
            "max": round(max([r.latency_ms for r in ok_results]), 2) if ok_results else 0.0,
        },
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "test_set": str(test_set_path),
        "summary": summary,
        "results": [r.__dict__ for r in results],
    }


def write_report(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"eval_report_{stamp}.json"
    md_path = out_dir / f"eval_report_{stamp}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    s = report["summary"]
    lines = [
        "# Chatbot Evaluation Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Test set: `{report['test_set']}`",
        "",
        "## Summary Metrics",
        "",
        f"- Total cases: **{s['total_cases']}**",
        f"- Successful executions: **{s['ok_cases']}**",
        f"- Exact match success: **{s['exact_match_success']:.2%}**",
        f"- Grounded answer success: **{s['grounded_answer_success']:.2%}**",
        f"- Unresolved rate: **{s['unresolved_rate']:.2%}**",
        f"- Wrong citation rate: **{s['wrong_citation_rate']:.2%}**",
        f"- Latency avg/p95/max (ms): **{s['latency_ms']['avg']} / {s['latency_ms']['p95']} / {s['latency_ms']['max']}**",
        "",
        "## Response Mode Distribution",
        "",
    ]

    dist = s.get("response_mode_distribution", {})
    if dist:
        for k, v in sorted(dist.items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"- `{k}`: {v}")
    else:
        lines.append("- None")

    lines.extend(["", "## Weak Spots", ""])
    weak = [
        r
        for r in report["results"]
        if r["status"] != "ok" or not r["grounded_success"] or r["wrong_citation"] or r["unresolved"]
    ]
    if weak:
        for r in weak:
            lines.append(
                f"- `{r['case_id']}` ({r['category']}): status={r['status']}, unresolved={r['unresolved']}, "
                f"grounded_success={r['grounded_success']}, wrong_citation={r['wrong_citation']}, source={r['answer_source']} {r['notes']}"
            )
    else:
        lines.append("- No obvious weak areas from this run.")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run chatbot evaluation harness")
    parser.add_argument("--test-set", type=Path, default=DEFAULT_TEST_SET)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    report = run_eval(args.test_set)
    json_path, md_path = write_report(report, args.out_dir)

    s = report["summary"]
    print("=== Chatbot Eval Summary ===")
    print(f"Total cases: {s['total_cases']}")
    print(f"OK cases: {s['ok_cases']}")
    print(f"Exact match success: {s['exact_match_success']:.2%}")
    print(f"Grounded answer success: {s['grounded_answer_success']:.2%}")
    print(f"Unresolved rate: {s['unresolved_rate']:.2%}")
    print(f"Wrong citation rate: {s['wrong_citation_rate']:.2%}")
    print(
        f"Latency (avg/p95/max ms): {s['latency_ms']['avg']} / {s['latency_ms']['p95']} / {s['latency_ms']['max']}"
    )
    print(f"Report JSON: {json_path}")
    print(f"Report MD:   {md_path}")


if __name__ == "__main__":
    main()
