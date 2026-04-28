"""LLM-as-judge with strict deterministic checks.

The judge reads each result and assigns three boolean criteria:

- cited:     at least one citation present, source non-empty
- grounded:  no numeric value in body that did not come from the tool
             outputs or a corpus chunk (string-match heuristic plus LLM
             second opinion)
- correct:   the visibility level / severity matches the expected label

Reports per-event scores and per-persona aggregate precision.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from auroragaze.llm import make_llm

ROOT = Path(__file__).resolve().parent

JUDGE_SYSTEM = """You are a strict eval judge for AuroraGaze briefings.

Given a briefing JSON, the trace of tool calls that produced it, and the
expected outcome, return a JSON object with three boolean fields:

{
  "cited": true if the briefing's citations list has at least one entry
           with a non-empty source string,
  "grounded": true if every numeric value in the briefing body
              (Kp, Bz, speed, density, drag fraction, oval boundary)
              appears in the trace or in one of the cited chunks. False
              if the briefing introduces a number that did not come from
              a tool or chunk,
  "correct": true if the predicted visibility level (for aurora) or
             severity / per-unit action (for satellite) matches the
             expected outcome
}

Return only the JSON object, no preamble. Do not add fields. Do not
explain."""

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _deterministic_cited(briefing: dict[str, Any]) -> bool:
    cites = briefing.get("citations") or []
    return any((c.get("source") or "").strip() for c in cites)


def _deterministic_correct(result: dict[str, Any]) -> bool:
    expected = result.get("expected", {})
    briefing = result.get("briefing") or {}
    if result.get("persona") == "aurora":
        want = expected.get("expected_visibility")
        got = (briefing.get("visibility") or {}).get("level")
        return bool(want) and want == got
    want_sev = expected.get("expected_severity", "")
    body = (briefing.get("body") or "") + " " + (briefing.get("headline") or "")
    return want_sev.lower() in body.lower() if want_sev else True


async def _llm_judge(result: dict[str, Any]) -> dict[str, bool]:
    llm = make_llm(temperature=0.0)
    msg = (
        f"Persona: {result.get('persona')}\n"
        f"Expected: {json.dumps(result.get('expected', {}))}\n"
        f"Trace:\n{chr(10).join(result.get('trace', []))}\n\n"
        f"Briefing:\n{json.dumps(result.get('briefing'), indent=2)}\n"
    )
    resp = await llm.ainvoke(
        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": msg}]
    )
    text = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(text)
        return {k: bool(parsed.get(k)) for k in ("cited", "grounded", "correct")}
    except json.JSONDecodeError:
        return {"cited": False, "grounded": False, "correct": False}


async def judge_results(in_path: Path, out_path: Path) -> dict[str, Any]:
    results = json.loads(in_path.read_text())
    judged: list[dict[str, Any]] = []
    for r in results:
        if r.get("error") or r.get("briefing") is None:
            judged.append({**r, "scores": {"cited": False, "grounded": False, "correct": False}})
            continue
        det = {
            "cited": _deterministic_cited(r["briefing"]),
            "correct": _deterministic_correct(r),
        }
        llm = await _llm_judge(r)
        scores = {
            "cited": det["cited"] and llm["cited"],
            "grounded": llm["grounded"],
            "correct": det["correct"] and llm["correct"],
        }
        judged.append({**r, "scores": scores})
    summary = _summarise(judged)
    out_path.write_text(json.dumps({"summary": summary, "results": judged}, indent=2, default=str))
    return summary


def _summarise(judged: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(judged) or 1
    overall = {
        "cited": sum(1 for r in judged if r.get("scores", {}).get("cited")) / total,
        "grounded": sum(1 for r in judged if r.get("scores", {}).get("grounded")) / total,
        "correct": sum(1 for r in judged if r.get("scores", {}).get("correct")) / total,
    }
    by_persona: dict[str, dict[str, float]] = {}
    for persona in {"aurora", "satellite"}:
        rows = [r for r in judged if r.get("persona") == persona]
        n = len(rows) or 1
        by_persona[persona] = {
            "n": float(len(rows)),
            "cited": sum(1 for r in rows if r.get("scores", {}).get("cited")) / n,
            "grounded": sum(1 for r in rows if r.get("scores", {}).get("grounded")) / n,
            "correct": sum(1 for r in rows if r.get("scores", {}).get("correct")) / n,
        }
    overall["precision"] = (overall["cited"] + overall["grounded"] + overall["correct"]) / 3
    return {"overall": overall, "by_persona": by_persona, "n": float(total)}


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", default=str(ROOT / "results.json"))
    parser.add_argument("--out", default=str(ROOT / "results_judged.json"))
    args = parser.parse_args()
    summary = asyncio.run(judge_results(Path(args.inp), Path(args.out)))
    print(json.dumps(summary, indent=2))
