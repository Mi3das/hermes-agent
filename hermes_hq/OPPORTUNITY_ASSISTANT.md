# HERMES HQ — Opportunity Assistant

A human-in-the-loop pipeline for finding and drafting legitimate income work.
Agents research and draft; **you** approve anything that touches money or goes
outbound. This document is deliberately honest about what the feature does and
does not do.

## What it actually does

- Stores "opportunities": a researched finding plus an agent-produced draft
  (e.g. a freelance gig + a drafted proposal; a content idea + a draft post).
- Runs each opportunity through an explicit, enforced state machine:

      draft → pending_review → approved → archived
                         └──→ rejected

- Classifies every opportunity's proposed next step. If that step would **send
  something outbound or touch money** (email, submit, bid, pay, buy, sell,
  transfer, sign up, …), it is hard-gated: it cannot be marked executable until
  a human approves it.
- Persists to `~/.hermes/hermes_hq/opportunities.json` atomically and
  thread-safely — the same proven pattern as `brain.py`.

## What it deliberately does NOT do

- It does **not** send emails, submit forms, place bids, trade, or move money.
  There is no code path in this module that performs an outbound or financial
  action. The "execute" step is left to you, manually, after approval.
- It does **not** auto-approve anything. The only way an item reaches
  `approved` is an explicit human call to the approve endpoint.
- It does **not** promise or generate income. It is a research + drafting +
  review surface. `est_value` is free-text you or the agent jot down — never a
  guarantee.

This matches your stated preference: semi-automatic, never act (send/spend)
without your approval.

## The gate (why you can trust it)

`opportunities.py` enforces three independent layers:

1. **State machine** — `_TRANSITIONS` only permits legal moves. You cannot jump
   `draft → approved`; it must pass through `pending_review`. Any other target
   raises.
2. **Risk classification** — `classify_risk()` flags outbound/financial action
   text and **fails safe**: an empty action isn't gated (nothing to run), but
   any ambiguous non-empty action defaults to "requires human review."
3. **Gate check** — `can_execute_outbound()` is the single source of truth the
   rest of the system must consult. It returns `allowed: true` **only** when a
   human has approved AND the gate flag is cleared.

All three are covered by `test_opportunity_gate.py` (22 checks, all passing),
which runs against a real temp `HERMES_HOME` — no mocks of the queue itself.

## How agents feed it (opt-in)

Normal missions are never captured. Only a mission whose prompt contains the
tag `[OPPORTUNITY]` has its result filed into the queue (as a `draft`, then
auto-submitted to `pending_review`). Example mission prompt:

    [OPPORTUNITY] Research 5 freelance Python scraping gigs posted this week
    on public job boards. For each, draft a short proposal in my voice. End
    with a line "PROPOSED NEXT STEP:" describing what I'd do to pursue it.

The Commander researches and drafts. You then review each captured item in the
dashboard / via the API and decide.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/opportunities` | List (filter `?state=` / `?pod=`) + stats |
| GET | `/api/opportunities/{id}` | One opportunity |
| POST | `/api/opportunities` | Create (starts as draft → pending_review) |
| POST | `/api/opportunities/{id}/approve` | **Human** approval — clears the gate |
| POST | `/api/opportunities/{id}/reject` | Human rejection |
| POST | `/api/opportunities/{id}/archive` | File away |
| GET | `/api/opportunities/{id}/can-execute` | Gate check (allowed only if approved) |
| DELETE | `/api/opportunities/{id}` | Remove |

No endpoint here sends anything outbound or moves money.

## Files

- `hermes_hq/opportunities.py` — the queue, state machine, risk gate.
- `hermes_hq/engine.py` — `self.opportunities` + `_maybe_capture_opportunity`.
- `hermes_hq/server.py` — the `/api/opportunities/*` endpoints.
- `hermes_hq/test_opportunity_gate.py` — real gate tests (run it any time).

## Run the tests

    source .venv/bin/activate
    python hermes_hq/test_opportunity_gate.py

Exit code 0 = the gate holds.

## Honest limitations / next steps

- "Find income" is only as good as the research mission you write and the job
  boards/sources the agent can actually reach. This module organises and gates
  the output; it does not magically discover money.
- The outbound "execute" step is intentionally not built. If you ever want a
  semi-automated send (e.g. draft an email for one-click sending), that should
  be a separate, explicitly human-triggered action that calls
  `can_execute_outbound()` first and still shows you the content before sending.
- The earlier "self-improvement" modules (`self_improvement.py`,
  `performance.py`, `adaptive.py`) are now partially wired to reality: the
  engine records **real** mission outcomes (success, duration, token/cost,
  failure reason) into the learning store via
  `engine._record_learning_outcome()`, keyed `commander:<model>`. The
  dashboard's "Commander Performance" panel reflects those real runs. The fake
  `seed_demo.py` is now guarded behind `HQ_ALLOW_FAKE_SEED=1` so it can no
  longer silently pollute real stats. (The `adaptive.py` / `performance.py`
  analytics helpers beyond basic recording are still not all consumed in the
  live loop — they're available but not yet surfaced.)
