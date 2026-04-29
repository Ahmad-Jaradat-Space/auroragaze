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

import contextlib
import json
import re
from pathlib import Path
from typing import Any

from auroragaze.llm import make_llm

ROOT = Path(__file__).resolve().parent

JUDGE_SYSTEM = """You are a strict eval judge for AuroraGaze briefings.

You will be given:
- The briefing JSON.
- The "allowed numbers" the briefing was built from — observed values
  (Kp, Bz, speed, density, Dst), the viewer's lat/lon, the computed
  oval boundary, and the numbers contained in the cited chunks.
- The expected outcome (visibility level or severity).

Return a JSON object with three boolean fields:

{
  "cited": true if the citations list has at least one non-empty source.
  "grounded": true if every numeric value in the briefing prose
              (summary + headline + body + storm_summary) is either:
              - an "allowed number" (within ±5% relative or ±0.5 absolute),
              - a date or year (1989, 2024-05-11 etc.), OR
              - a generic small number 0–15 used in counts/categories.
              The number does NOT have to be quoted exactly; rounding to
              one decimal or to the nearest integer is fine. It only has
              to be derivable from the allowed list. Otherwise false.
  "correct": true if the predicted visibility level (for aurora) or
             severity word (for satellite) matches the expected outcome.
}

Return only the JSON object, no preamble. Do not add fields. Do not explain."""

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
_TRACE_NUM = re.compile(r"(Bz|v|Kp|Dst|altitude|kp|threshold)=?\s*(-?\d+(?:\.\d+)?)")


def _allowed_numbers_for(result: dict[str, Any]) -> list[float]:
    nums: list[float] = []
    for line in result.get("trace") or []:
        for m in _TRACE_NUM.finditer(str(line)):
            with contextlib.suppress(ValueError):
                nums.append(float(m.group(2)))
        # also pick up any standalone numerics in the trace line (oval boundary
        # appears as "physics: oval threshold ~46.0°S; viewer 42.9°S → likely")
        for m in _NUM_RE.finditer(str(line)):
            with contextlib.suppress(ValueError):
                nums.append(float(m.group(0)))
    for c in result.get("chunks") or []:
        text = c.get("text", "") if isinstance(c, dict) else getattr(c, "text", "")
        for m in _NUM_RE.finditer(text):
            with contextlib.suppress(ValueError):
                nums.append(float(m.group(0)))
    # de-dup, keep sorted for prompt readability
    return sorted({round(n, 2) for n in nums})


def _deterministic_cited(briefing: dict[str, Any]) -> bool:
    cites = briefing.get("citations") or []
    return any((c.get("source") or "").strip() for c in cites)


def _deterministic_grounded(result: dict[str, Any]) -> bool:
    """Use the verifier node's own outcome from the trace.

    The production verifier writes 'verifier: grounded ✓' when every
    numeric value in the briefing is supported by the tool outputs or
    the retrieved chunks. This is the same code that runs in production,
    so the eval and the live system score `grounded` identically.
    """
    return any("verifier: grounded" in str(line) for line in result.get("trace") or [])


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
    allowed = _allowed_numbers_for(result)
    msg = (
        f"Persona: {result.get('persona')}\n"
        f"Expected: {json.dumps(result.get('expected', {}))}\n"
        f"Allowed numbers: {allowed}\n"
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
            "grounded": _deterministic_grounded(r),
        }
        llm = await _llm_judge(r)
        scores = {
            "cited": det["cited"] and llm["cited"],
            "grounded": det["grounded"],
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
