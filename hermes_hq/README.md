# HERMES HQ

A visualised, fully-automated **multi-agent ecosystem** with the Hermes agent as
the lead head agent (the **HQ Commander**).

You give HQ a mission. The Commander — a real Hermes `AIAgent` — autonomously
decomposes it and dispatches specialist **subagents in parallel** using the
repo's real `delegate_task` engine. A live web dashboard visualises the whole
swarm: the Commander at the centre, subagents orbiting as nodes that spawn,
pulse while working, and settle to done/failed — all driven by the core's own
`list_active_subagents()` registry, so the picture never drifts from reality.

```
        ┌──────────────────────────────────────────────┐
        │                  HERMES  HQ                    │
        │  mission ─▶ HQ COMMANDER ─▶ delegate_task ─▶   │
        │                  │                              │
        │        ┌─────────┼─────────┐                    │
        │     subagent  subagent  subagent  (live graph)  │
        └──────────────────────────────────────────────┘
```

## What's real here

- **Real engine.** The Commander is a genuine `AIAgent` resolved through the
  same `resolve_runtime_provider` path the CLI uses — it runs on whatever
  provider/model you've configured (`hermes model`). No mocks.
- **Real delegation.** Subagents are spawned by the in-tree `delegate_task`
  tool with isolated context, restricted toolsets and their own terminal
  sessions. The Commander decides the decomposition.
- **Real telemetry.** The live graph + activity feed stream from
  `list_active_subagents()`, `is_spawn_paused()` and the mission bookkeeping —
  the same observability surface the TUI `/agents` overlay uses.
- **Real controls.** Pause/resume new spawns (`set_spawn_paused`) and interrupt
  a single running subagent (`interrupt_subagent`) straight from the UI.
- **Nested swarms.** A live **nesting-depth slider** sets
  `delegation.max_spawn_depth`. At depth ≥ 2 the Commander can delegate a broad
  sub-task with `role='orchestrator'`, and that subagent spawns its own workers
  — the graph renders the full multi-level tree (deeper nodes are smaller and
  orbit their actual parent, not HQ).
- **Per-agent live output.** Click any node to see that agent's live tool
  activity (thinking, tool calls, sub-delegations, completion) streamed in real
  time — captured via the Commander's `tool_progress_callback`, the same event
  stream the TUI overlay consumes. Output persists after the agent finishes.
- **Live Commander reasoning.** A **Commander tab** streams the lead agent's own
  tokens in real time (via `AIAgent.chat(stream_callback=…)`) so you watch HQ
  think and synthesise, not just its subagents.
- **Mission cancel.** Stop a running mission from the UI — it calls
  `AIAgent.interrupt()` to gracefully abort the Commander's tool loop and any
  in-flight subagent work.
- **Persistent history.** Missions (prompt, status, result, metrics, Commander
  transcript) are saved to `~/.hermes/hermes_hq/missions.json` and reload on
  restart, so your operation log survives app restarts. A mission left
  "running" when the app dies is marked `interrupted` on reload.
- **Live ecosystem stats.** A header stats strip streams aggregate metrics:
  total/running/completed missions, success rate, active agents, total
  subagents spawned, tool calls, average duration, and uptime.
- **Per-mission metrics.** Each mission tracks subagents spawned, subagent tool
  calls, peak concurrency, max nesting depth, and wall-clock duration — shown in
  a metrics grid in the detail panel.
- **Export.** One click (or `GET /api/export`) dumps the full ecosystem state —
  HQ info, aggregate stats, and every mission — as JSON for archival.
- **Commander readiness.** `/api/info` reports the real resolved provider/model
  and two distinct states — `ready` (credentials resolve, HQ can run on demand)
  and `online` (the Commander agent is built and live) — via a cheap credential
  probe that runs **without** building the agent or hitting the network. The
  header shows a live status dot (green online · amber ready · red offline), and
  when no provider resolves an **offline banner** explains the fix (`hermes
  model` / `~/.hermes/.env`) with a one-click retry; launching is blocked until
  HQ is ready. The probe caches success and re-checks on failure, so fixing your
  config is reflected without a restart.
- **Quality-of-life.** Mission filter/search, inline delete, `⌘/Ctrl+Enter` to
  launch, toast notifications, and a polished dark command-center theme.
- **Mission re-run.** Re-launch any finished mission's prompt as a fresh mission
  with one click (`POST /api/mission/{id}/rerun`).
- **Mission template library.** A categorized preset browser (Research,
  Engineering, Product & Launch, Content, Analysis) — pick a category, click
  **▤ templates**, and load a ready-to-run multi-agent mission into the console.
- **Theme system.** Cycle through four palettes — Midnight, Ember, Matrix, Light
  — via the **◐ THEME** button or the `T` shortcut; the choice persists in
  `localStorage`.
- **Clean AppleScript quit.** The desktop bundle is a stay-open AppleScript
  applet, so `tell application "HERMES HQ" to quit` (Cmd-Q, logout, shutdown,
  uninstallers) fires an `on quit` handler that calls `POST /api/shutdown` for a
  graceful stop — state is flushed and the server exits cleanly with no orphans.

## The agent-company model (gBRAIN · Org · Pods)

HERMES HQ implements the three pillars of the "agent company inside an agency"
design — all persisted to `~/.hermes/hermes_hq/gbrain.json` and editable live
from the dashboard:

- **gBRAIN (agency brain).** A shared knowledge store — playbooks, voice/tone,
  conventions, frameworks. Open the **🧠 BRAIN** drawer to add titled,
  optionally-tagged entries. The brain is composed into every mission so the
  whole company applies the same standards. Crucially, the brain is injected
  into the mission's **user message**, never the system prompt, so the
  Commander's cached prefix stays byte-stable (prompt caching is sacred).
- **Org chart (Department Verticals).** A configurable taxonomy of
  Verticals → Specialists → Scoped Sub-agents, rendered in the **▦ Org Chart**
  center view and seeded with Content / Lifecycle Email / Technical SEO /
  Paid Ads. The Commander is told which verticals/specialists exist and is
  instructed to route each sub-task to the right one and name it in the
  subagent's goal — so the swarm maps to the org chart. Add/remove verticals
  live.
- **Client Pods (isolated workspaces).** Each pod is its own workspace with its
  own brain entries and (optionally) provider/model. The **◑ POD** header
  selector scopes the mission list and new launches to one pod. A pod's brain
  composes *on top of* the agency brain for its missions, and the Commander is
  told to keep each pod's context isolated — no context bleeding across clients.
  The `default` ("Agency") pod always exists and can't be deleted.

## Run it

```bash
source .venv/bin/activate          # or venv/
python -m hermes_hq                 # http://127.0.0.1:8787
```

Options:

```bash
python -m hermes_hq --port 9000 --provider anthropic --model claude-opus-4-8
```

Then open the URL, type a mission (e.g. *"Research the top 3 open-weight LLMs
and summarise each"*), and hit **LAUNCH MISSION**. Watch the Commander fan the
work out to subagents in real time.

## Architecture

| File | Role |
|------|------|
| `engine.py` | Bootstraps the long-lived HQ Commander agent; runs each mission on a background thread via `AIAgent.chat(stream_callback=…)` (full agentic loop, live token stream); composes the brain context into the mission's user message; persists history; tracks per-mission metrics; cancels via `AIAgent.interrupt()`. |
| `brain.py` | `HQBrain`: thread-safe, JSON-persisted store for the agency brain (knowledge entries), the org chart (verticals → specialists → sub-agents), and client pods (isolated workspaces). Composes the per-mission/per-pod context block. |
| `server.py` | FastAPI app: mission endpoints (+ pod scoping) + SSE live stream (subagents + missions + stats + brain) + pause/interrupt/cancel/delete/rerun + `/api/stats` + `/api/export` + `/api/brain` + `/api/org` + `/api/pods` + `/api/shutdown`. |
| `static/index.html` | Self-contained dashboard: force-directed agent graph, org-chart view, mission console, stats strip, pod selector, gBRAIN drawer, Activity/Commander tabs, per-mission metrics grid. Zero external JS deps. |
| `__main__.py` | `python -m hermes_hq` launcher. |
| `desktop/` | macOS `.app` bundle (stay-open AppleScript applet + shell launcher) that owns the server lifecycle and shuts down cleanly with no orphans. |

## Configuration

HQ inherits everything from your Hermes config. The relevant knobs (in
`config.yaml` under `delegation:`) shape the ecosystem:

- `max_concurrent_children` — how many subagents run in parallel (default 3).
- `max_spawn_depth` — raise to 2+ to let `role='orchestrator'` subagents spawn
  their own workers (nested swarms).

The dashboard header shows the live values.

## Notes

- Credentials load from `~/.hermes/.env`; the resolver mirrors CLI startup.
- HQ runs `skip_memory=True` / `skip_context_files=True` so missions are clean
  and don't write to your shared `MEMORY.md`.
- This is an *edge* app: it lives in its own `hermes_hq/` package and only
  imports the public-ish surface of the core (`AIAgent`, the delegate tool's
  registry helpers). It adds **zero** new core model tools.
