# Eval calibration

The judge for AuroraGaze checks three boolean criteria per briefing:

| field      | what it checks                                                              | check method                                       |
|------------|-----------------------------------------------------------------------------|----------------------------------------------------|
| cited      | the briefing has a non-empty `citations[].source`                           | deterministic + LLM cross-check                    |
| grounded   | every numeric value in the body came from a tool output or corpus chunk     | LLM judge (string-match heuristic too rough alone) |
| correct    | predicted visibility / severity matches the expected outcome on the event   | deterministic equality + LLM cross-check           |

Both deterministic and LLM checks must agree for `cited` and `correct` to
score 1. For `grounded` only the LLM judge votes; we did not write a
deterministic numeric tracer because corpus snippets quote numbers in
prose, not tagged form.

## Threshold

CI fails the build if **overall precision < 0.80**. Per-persona precision
is reported but not gated; persona-specific drift is investigated on the
PR rather than auto-blocked.

## How the threshold was picked

A first run on the 20-event golden set with a deliberately weakened
composer prompt (no "do not invent numbers" rule, citations optional)
scored 0.55 overall. Tightening the rules to the current `prompts.py`
got us above 0.85 on a hand sample of 5 events; we set the gate at 0.80
to leave headroom for corpus drift.

## Where the judge can be wrong

- "Grounded" judgement is conservative: when a paraphrase replaces the
  exact number with a category ("Kp 9 / extreme"), the judge can flag
  it as ungrounded. We accept this as a quality bias — false negatives
  here surface real risk.
- "Correct" for satellite scoring matches a free-text severity word
  (low / moderate / high / extreme) inside the body. A briefing that
  uses synonyms can score false-negative; we audit a sample of the
  failures rather than expanding the synonym list.
