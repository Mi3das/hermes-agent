# Technical and Operational Requirements: Multi-Agent Dashboard

**Document Version:** 1.0  
**Date:** June 13, 2026  
**Audience:** Operations Teams, Platform Engineers, Product Managers  
**Scope:** Dashboard feature set, observability surface, and operational control plane for distributed multi-agent systems

---

## Executive Summary

A multi-agent dashboard must present real-time visibility into a distributed swarm of collaborative agents while enabling active management and intervention. This document defines the technical requirements and operational-product interface that bridge what ops teams must see, control, and measure versus what the system can efficiently surface.

The dashboard is **not** a passive monitoring layer—it is an active control plane that directly integrates with the core agent runtime (`delegate_task`, `list_active_subagents()`, `AIAgent.interrupt()`, pause/resume knobs) so operational actions are performed at the source, not by polling or post-hoc replication.

---

## 1. Operational Data Surface (What Ops Must See)

### 1.1 Agent State Inventory

**Requirement:** Real-time visibility into every agent in the swarm, with atomic state transitions and hierarchical context.

**Data Points:**
- **Agent Identity & Hierarchy**
  - Agent ID (unique, stable across restarts)
  - Role / specialist classification (e.g., "Researcher", "Engineer", "Writer")
  - Parent agent ID (for nested delegation; null for root Commander)
  - Delegation depth (for rendering hierarchy; count from root)
  - Spawned timestamp and elapsed duration

- **Execution State (atomic enum)**
  - `spawned` → `running` → `completed` | `failed` | `interrupted`
  - State timestamp (precise to millisecond for latency calculations)
  - Terminal state reason (error message, cancellation signal, timeout)

- **Work Context**
  - Goal / task description (human-readable, up to 500 chars)
  - Assigned toolset(s) (e.g., `["web", "terminal"]`)
  - Nesting depth (0 for root, incremented per level of delegation)

- **Resource Allocation**
  - Execution thread ID (for ops debugging process-level issues)
  - Estimated time-to-completion (from performance history, if available)
  - Memory footprint (optional, for scheduling resource constraints)

**Freshness:** State updates streamed in real-time via SSE (< 50 ms latency from state change to UI push).

**Storage:** Snapshot persisted at mission completion; live state held in memory during execution.

**Fallback:** If streaming breaks, auto-reconnect SSE every 5s and backfill missed state transitions.

---

### 1.2 Task Queues & Work Distribution

**Requirement:** Understand what work is pending, how it is routed, and why agents are idle or blocked.

**Data Points:**
- **Active Task Set (per root mission)**
  - Total tasks spawned (cumulative count)
  - Tasks in flight (running now)
  - Tasks pending (queued, waiting for concurrency slot)
  - Max concurrency setting (e.g., 3 parallel children)
  - Queue fairness / age of oldest pending task

- **Routing Metadata**
  - Which task was routed to which specialist/subagent (audit trail for delegations)
  - Reason for routing (if Commander logs it; e.g., "Content Vertical → Blog Writer → Outline Generator")
  - Toolset restrictions applied to that subagent

- **Blocking/Contention Signals**
  - Count of tasks waiting for concurrency slots
  - Age of longest-waiting task (milliseconds)
  - If spawn is paused, reason and pause duration

**Freshness:** Updated on each delegation call and completion; aggregated per-mission.

**Storage:** Logged as part of mission metrics; current queue state held in-memory.

---

### 1.3 Execution Logs & Tool Activity

**Requirement:** Drill down from a mission to a single agent's tool invocations, reasoning, and output to debug failures and understand how work was done.

**Data Points per Agent:**
- **Tool Call Stream** (one entry per tool invocation)
  ```
  {
    "timestamp": 1718246400123,
    "tool_name": "web_search",
    "status": "invoked" | "completed" | "failed",
    "input": { "query": "..." },
    "output": "...", (first 10 KB; full output stored separately if > threshold)
    "duration_ms": 1540,
    "token_count": { "input": 150, "output": 320 }
  }
  ```

- **Reasoning Trace** (Agent's thinking tokens if available)
  - Streamed in real-time if model provides it (e.g., Claude's `thinking` block)
  - Stored separately (not in main event log; stored on disk for archival)

- **Sub-task Delegations** (if this agent spawned children)
  - List of child agents spawned, their goals, and outcomes

- **Terminal Output** (if agent ran shell commands)
  - stdout/stderr captured, timestamped, truncated to last 100 KB in-memory

**Freshness:** Tool calls streamed in real-time via SSE; reasoning/terminal output buffered (100 ms window for batching).

**Storage:** Streamed to client for live display; persisted to disk at mission end in compressed JSON.

**Retention:** Current mission kept in-memory; archived missions (> 7 days old) moved to cold storage or deleted per ops policy.

---

### 1.4 Error Tracking & Failure Diagnostics

**Requirement:** Surface actionable error signals so ops can triage and remediate without replaying the entire mission.

**Data Points:**
- **Error Events** (per agent failure)
  ```
  {
    "timestamp": 1718246400523,
    "agent_id": "sub_xyz",
    "error_type": "ToolExecutionError" | "TimeoutError" | "AuthenticationError" | "ModelError" | "InterruptedError",
    "message": "...",
    "recoverable": true | false,
    "recovery_action": "retry" | "fallback" | "escalate_to_human",
    "attempt_count": 2
  }
  ```

- **Failure Cascade Tracking**
  - If one agent's failure caused a parent to cancel its remaining children (explain why)
  - Root-cause determination (e.g., "third-party API timeout" vs. "credential expired" vs. "invalid input from parent")

- **Retry State**
  - How many times a tool or delegation was retried
  - Retry policy applied (exponential backoff, max attempts, etc.)
  - Success on retry vs. terminal failure

- **Timeout Events**
  - Agent timeout threshold (from config)
  - Actual vs. expected duration
  - Which subagent or tool exceeded the SLA

**Freshness:** Real-time on error occurrence (< 100 ms latency).

**Storage:** Persisted to mission history; exported in error reports.

**Alerting Hooks:** System provides ingestion for ops platforms (Datadog, New Relic, etc.) via webhook or event stream.

---

### 1.5 Latency & Performance Telemetry

**Requirement:** Measure and expose where time is spent so ops can optimize agent configuration, toolset choices, and routing.

**Data Points per Agent:**
- **Timing Breakdown**
  ```
  {
    "wall_clock_duration_ms": 5420,
    "agent_thinking_ms": 1200,      // model inference time
    "tool_execution_ms": 3100,      // time in actual tool calls
    "tool_overhead_ms": 800,        // formatting, parsing, validation
    "queue_wait_ms": 320            // time this agent spent waiting for concurrency slot
  }
  ```

- **Per-Tool Latency** (aggregated across all invocations of one tool by one agent)
  - Tool name, count of calls, min/max/median/p95 duration
  - Slowest tools highlighted for ops review

- **End-to-End Mission Duration Breakdown**
  - Time from mission start to first agent spawn
  - Time from first spawn to all agents done
  - Time from completion to result delivery
  - Top time-consuming agents / critical path

- **Concurrency Efficiency**
  - Total wall-clock duration vs. sum of agent durations (ideal = 1.0 / actual concurrency factor)
  - Idle slots: how many times was the concurrency pool not full?

**Freshness:** Calculated at agent completion; mission aggregates updated continuously.

**Storage:** Persisted per-mission; aggregated over time for trend analysis.

**Reporting:** Exposed via `/api/mission/{id}/metrics` and bulk export; suitable for BI/analytics ingestion.

---

## 2. Agent Management & Coordination (Operational Controls)

### 2.1 Spawning & Lifecycle Knobs

**Requirement:** Ops must be able to adjust agent spawning behavior without code changes; the dashboard provides real-time tuning.

**Controllable Parameters:**
- **Max Concurrency** (`max_concurrent_children`)
  - Default: 3 parallel subagents
  - Ops can adjust: 1 to 16 (tunable via config.yaml)
  - Effect: Immediate on next spawn; in-flight agents unaffected
  - Use case: Throttle during high API costs, increase during low-latency periods

- **Max Nesting Depth** (`max_spawn_depth`)
  - Default: 1 (flat: only root + direct children)
  - Ops can raise to 2+ for orchestrator-style nested delegation
  - Effect: Immediate; affects next delegation call
  - Use case: Enable hierarchical teams for complex multi-step missions

- **Spawn Pause / Resume** (`is_spawn_paused()` gate)
  - Ops can pause all new spawns without killing in-flight agents
  - In-progress subagents continue; new ones are held in queue
  - Use case: Stop new work during credential rotation or maintenance
  - Effect: Immediate; queued tasks are held until resumed

- **Spawn Rate Limiting** (optional enhancement)
  - Max spawns per second (to smooth API call ramps)
  - Exponential backoff if spawning fails repeatedly

**Implementation Path:**
- Settings persisted to `config.yaml` (durable across restarts)
- Runtime override via CLI_CONFIG in-memory dict (immediate effect without reload)
- Dashboard UI sliders/toggles with live value feedback

**Audit Trail:** All changes logged with timestamp, user (if available), old/new values.

---

### 2.2 Routing & Specialist Assignment

**Requirement:** Understand how the Commander routes work to specialists and provide ops with the ability to configure/override routing logic.

**Data Points:**
- **Specialist Registry** (from org chart + library)
  - Department verticals (e.g., "Content", "Technical SEO")
  - Specialists per vertical (e.g., "Blog Writer", "On-Page Specialist")
  - Scoped sub-agents per specialist
  - Available toolsets per specialist role

- **Routing Decision Log** (per delegation)
  - Which vertical/specialist was selected for this task
  - Confidence score (if Commander provides one)
  - Alternative routing options considered
  - Reason for final choice (from Commander's reasoning, if captured)

- **Mismatch Detection** (optional)
  - If a task failed and could have succeeded with a different specialist, flag it for feedback

**Operational Levers:**
- **Manual Specialist Override**
  - Ops can force a specific specialist assignment for a new mission (e.g., "Always use Engineer for coding tasks")
  - Persisted as a rule in the org chart

- **Specialist Availability**
  - Mark a specialist as unavailable (e.g., maintenance) so new tasks skip them
  - Adjust max concurrent tasks per specialist independently

- **Toolset Assignments**
  - Review which toolsets each specialist can access
  - Add/remove toolsets dynamically (with approval gate for high-risk roles)

---

### 2.3 Interruption & Cancellation Primitives

**Requirement:** Ops must be able to stop work—either one agent or an entire mission—cleanly and immediately.

**Operations:**
- **Interrupt Single Agent** (subagent_id)
  - Gracefully abort one running agent (via `AIAgent.interrupt()`)
  - Does NOT kill its children; children remain in flight and complete/fail on their own
  - Result: Agent marked as `interrupted`, failure reason recorded
  - Time to interrupt: < 500 ms (must set interrupt flag + break out of current tool call)

- **Cancel Entire Mission** (mission_id)
  - Interrupt the root Commander agent
  - All in-flight subagents are left in flight but no new spawns are created
  - Result: Mission marked as `cancelled`, timestamp recorded
  - Use case: User decides mid-flight that the mission is no longer needed

- **Kill by Age** (advanced)
  - Ops can set a max age for running agents; agents exceeding it are interrupted
  - Use case: Safety cap to prevent runaway jobs during debugging

- **Cascade Control**
  - Option: When interrupting an orchestrator, do also interrupt its children? (default: no, let them finish)
  - Audit each cascade decision

**Constraints:**
- Interrupt is graceful, not forceful; allows cleanup and logging
- No forced process kills (defeats observability)
- Failed interrupt (tool already done) is not an error; logged as benign race

---

## 3. Monitoring & Observability (Real-Time Surface)

### 3.1 Live Dashboard Visuals

**Requirement:** Real-time visual representation of the swarm for ops narrative understanding and incident triage.

**Visual Elements:**
- **Force-Directed Agent Graph**
  - Nodes: each agent (sized by nesting depth; root larger than children)
  - Edges: delegation relationships (parent → child)
  - Color coding by state: `spawned` (teal), `running` (pulse/glow), `completed` (green), `failed` (red), `interrupted` (yellow)
  - Animation: nodes animate into existence on spawn, settle to final state on completion
  - Interactivity: click node to open side panel with agent's detailed logs and metrics

- **Activity Feed**
  - Reverse-chronological list of recent events (agent spawned, tool executed, error occurred, mission completed)
  - Each event is a terse 1-liner with a link to drill down
  - Filterable by agent, by event type, by mission
  - Auto-scroll if live (pause on scroll, resume on new event if at bottom)

- **Stats Strip (Header)**
  - Ecosystem-level aggregates (updated every 1−5s):
    - Missions (total / running / completed / failed)
    - Agents (active / total spawned / success rate)
    - Tool calls (cumulative, last hour)
    - Average mission duration
    - Uptime (since dashboard start)

- **Per-Mission Panel**
  - Status badge (running / completed / failed / cancelled)
  - Progress bar (agents spawned / completed)
  - Metrics grid: subagent count, tool calls, peak concurrency, max depth, duration
  - Action buttons: pause/resume, interrupt, cancel, delete, re-run, export

- **Org Chart View** (optional tab)
  - Tree visualization of the Department Verticals → Specialists → Sub-agents taxonomy
  - Overlay: live agent assignments (which specialists are working right now?)
  - Drag-and-drop reordering (for ops with edit permissions)

**Freshness:** Graph updates via SSE every 50−100 ms when agents are spawning/completing; stats every 1−5 s.

---

### 3.2 Real-Time Event Stream (SSE)

**Requirement:** Server-sent events push agents' state changes to the dashboard without polling.

**Event Schema:**
```json
{
  "type": "agent_spawned|agent_state_change|tool_called|error_occurred|mission_state_change|stats",
  "timestamp": 1718246400123,
  "payload": { ... }
}
```

**Events:**
- `agent_spawned`: New agent created, includes ID, parent, goal, toolset
- `agent_state_change`: Agent transitioned to a new state (running, completed, failed, etc.)
- `tool_called`: Tool invocation (with input, output summary, duration)
- `error_occurred`: Error event with type, message, recoverable flag
- `mission_state_change`: Mission status changed (running, completed, failed, cancelled)
- `stats`: Aggregate stats pushed every N seconds

**Backpressure / Falloff:**
- If client can't keep up, server buffers events for 30 seconds max, then drops oldest
- Client detects connection loss, exponential backoff reconnect
- On reconnect, client requests missed events via HTTP fallback (e.g., `GET /api/mission/{id}/events?since=1718246400000`)

**Security:**
- SSE endpoint requires authentication (same as dashboard session)
- No sensitive data in event stream (credentials, API keys never transmitted)

---

### 3.3 Drill-Down: Per-Agent Live Output

**Requirement:** Click any agent in the graph and see its live tool activity as it happens.

**Output Panel Content:**
- **Agent Metadata**
  - ID, role, parent, goal, toolset, state, timestamps

- **Tool Activity Log** (live)
  - List of tool calls in execution order
  - Expandable entries showing full input/output
  - Color-coded by status (pending yellow, completed green, failed red)

- **Reasoning Trace** (if available)
  - Model's thinking tokens (Claude extended thinking, o1-style)
  - Displayed in a collapsible section

- **Terminal Output** (if command-line tools were used)
  - Last 50 KB of stdout/stderr in monospace
  - Auto-scroll to bottom; pause on click
  - Copy button for full output

- **Sub-Delegations** (if this agent spawned children)
  - List of child agents with their status and outcome
  - Click to drill down further

**Update Frequency:** On each tool event (no batching; < 100 ms latency).

**Storage During Session:** Held in memory (browser + server); persisted at mission end.

---

### 3.4 Metrics Export & Long-Term Analytics

**Requirement:** Ops can export and archive mission data for post-hoc analysis, trend detection, and SLA tracking.

**Export Formats:**
- **JSON** (complete, detailed)
  - Every mission's full metadata, state transitions, metrics, and agent activity
  - Suitable for data pipeline ingestion

- **CSV** (tabular, for spreadsheet analysis)
  - One row per mission, columns: mission_id, status, start_time, duration, agents_spawned, success_rate, etc.

- **Prometheus Metrics** (live scrape)
  - Exposed at `/metrics` in OpenMetrics format for Prometheus ingestion
  - Gauges: agents_active, missions_running, api_calls_total
  - Histograms: agent_duration_ms, tool_latency_ms
  - Counters: missions_total, errors_total, subagents_spawned_total

**Retention Policy:**
- Live missions: in-memory (full resolution)
- Completed missions (< 24 h): disk (JSON, full resolution)
- Completed missions (24 h−7 d): disk (JSON, trimmed—remove tool output details)
- Completed missions (> 7 d): move to cold storage (ZIP archives) or delete per ops policy

---

## 4. Data Freshness & Consistency Requirements

### 4.1 Freshness Tiers

**Tier 1: Real-Time (< 50 ms latency)**
- Agent state transitions (spawned, running, completed)
- Error events
- Current tool execution progress

**Tier 2: Near-Real-Time (100−500 ms batched)**
- Tool output (buffered, sent in batch every 100 ms)
- Reasoning tokens (streamed in chunks)
- Metrics recalculated every 500 ms

**Tier 3: UI Refresh (1−5 s)**
- Aggregate stats (mission count, total agents, uptime)
- Dashboard layout reflow (only if needed)

**Tier 4: Periodic (5−60 s)**
- Disk checkpoint of mission state (every 10 s during execution)
- Garbage collection of old sessions
- Credential probe for "ready/online" status

### 4.2 State Consistency Guarantees

**Requirement:** The dashboard state never drifts from the true runtime state; ops decisions are always made on current ground truth.

**Mechanism:**
- **Source of Truth:** The core's `list_active_subagents()` registry is the canonical state (updated in-process, thread-safe)
- **Dashboard Sync:** Server polls this registry on every SSE event push (< 50 ms stale on worst case)
- **Audit Trail:** All state transitions logged to disk with timestamps so ops can trace causality
- **Reconciliation:** On SSE reconnect, client fetches full mission state via HTTP to re-sync in-memory model

**Conflict Resolution:**
- If dashboard believes an agent is running but runtime says it completed: trust runtime, update dashboard
- Log all reconciliations for ops review
- Trigger alert if reconciliation rate exceeds threshold (indicates deeper issue)

### 4.3 Eventual Consistency for Historical Data

**Requirement:** Completed missions' data (logs, metrics) will eventually be fully flushed to disk, but may lag behind real-time display while mission is in flight.

**Implementation:**
- During execution: Streaming data held in memory for low-latency display
- At completion: Atomic write of mission state to `missions.json` (durable, transactional)
- Post-completion: Separate thread compresses logs/tool output to cold storage in background

**Ops Implication:** If dashboard process crashes mid-mission, in-flight data is lost (accepted risk; can re-run mission). Completed missions are always preserved.

---

## 5. Technical Constraints & Risks

### 5.1 Scalability Challenges

**Challenge: Agent Graph Rendering at Scale**
- Force-directed graph rendering is O(n²) on interactions; limit live graph to 50 agents max
- Beyond that, use hierarchical layout (tree) or virtual scrolling
- **Mitigation:** Cap concurrent children; use org chart view for large swarms

**Challenge: Event Stream Backpressure**
- Dashboard + server may not keep up with hundreds of tool calls per second
- **Mitigation:** Buffer events server-side (drop oldest if > 30 s backlog); batch tool events every 100 ms on client

**Challenge: Memory Footprint**
- 1 million tool calls = ~500 MB in JSON format
- 100 concurrent missions × 1000 calls/mission = 50 GB without pruning
- **Mitigation:** Streaming straight to disk; keep only current mission in-memory; archive old missions immediately

**Challenge: Database Throughput**
- If using a persistent backend (not file-based), write load from many agents can saturate DB
- **Mitigation:** In-memory cache + periodic batch writes; or use time-series DB (InfluxDB, Prometheus)

---

### 5.2 Real-Time Update Challenges

**Challenge: SSE Connection Stability**
- Network interruptions, reverse-proxy timeouts, browser sleep
- **Mitigation:** Heartbeat ping every 15 s; client detects gaps and auto-reconnects with exponential backoff (max 30 s)

**Challenge: Clock Skew**
- Server and client clocks may differ; timestamps comparisons fail
- **Mitigation:** Use server-provided timestamps in all events; client only uses for UI display, not logic

**Challenge: Out-of-Order Events**
- High-latency paths may deliver events out of order (esp. if SSE buffers and client reconnects)
- **Mitigation:** Include sequence number (logical clock) in each event; re-order on client if out of order detected

---

### 5.3 State Consistency & Correctness

**Challenge: Race Conditions in Interrupt**
- Ops clicks "Interrupt" button; agent is already completing its last tool call
- **Mitigation:** Interrupt is idempotent; if agent is not interruptible, request returns error but dashboard doesn't break

**Challenge: Inconsistent Nested Hierarchy**
- Commander spawns child A, which spawns child B, but parent-child edges are recorded out of order
- **Mitigation:** Client-side graph rendering handles missing edges gracefully (render as orphan node); server reconciles on next query

**Challenge: Lost State on Crash**
- Dashboard server crashes mid-mission; in-memory agent list vanishes
- **Mitigation:** Mission state is persisted to disk every 10 s; on restart, in-flight missions are marked `interrupted` and re-loadable

---

### 5.4 Operational Risks

**Risk: Operator Mistakes**
- Ops accidentally pauses spawn, disrupting workflow
- **Mitigation:** Confirmation dialog for destructive actions (pause, cancel, interrupt); audit trail of all actions; undo buffer (last 5 actions reversible)

**Risk: Credential Rotation**
- Provider API key expires during a mission; dashboard shows agents as hung
- **Mitigation:** Monitor auth errors in real-time; surface "credentials stale" banner; provide "re-auth" action in dashboard

**Risk: Resource Exhaustion**
- Too many concurrent agents or API calls cause 429 / rate limit errors
- **Mitigation:** Monitor rate-limit responses; auto-throttle concurrency on detection; alert ops before hitting hard limit

**Risk: Information Overload**
- Dashboard overwhelmed with tool output; ops can't find the critical error signal
- **Mitigation:** Intelligent filtering (show only errors/warnings by default); full-text search; tagging/labels

---

## 6. Technical-Product Interface: Feature Mapping

### 6.1 What Ops Needs → What We Must Build

| Ops Need | Feature | Technical Component | Data Source |
|----------|---------|---------------------|-------------|
| See running agents now | Live graph | SSE + force-directed canvas | `list_active_subagents()` |
| Know what failed | Error feed | Alert stream | Error events from core |
| Find the bug | Agent drill-down + logs | Side panel + log viewer | Mission event log JSON |
| Adjust concurrency | Slider control | Input field + immediate apply | Config.yaml + CLI_CONFIG override |
| Stop a runaway agent | Interrupt button | POST /interrupt/{agent_id} | `AIAgent.interrupt()` call |
| Track over time | Export + metrics | CSV / JSON / Prometheus | missions.json + in-memory state |
| Understand routing | Org chart + decision log | Tree view + sidebar | brain.json + engine logs |
| Know uptime | Status dashboard | Stats strip + health check | Aggregated counters |

### 6.2 API Contract

**Auth & Health:**
- `GET /api/info` → Provider/model + config knobs (no credentials)
- `GET /api/health` → uptime, last mission, active agents

**Missions:**
- `POST /api/mission` → Start mission (returns mission_id)
- `GET /api/missions` → List missions (paginated, filterable)
- `GET /api/mission/{id}` → One mission's full state
- `POST /api/mission/{id}/cancel` → Interrupt entire mission
- `POST /api/mission/{id}/rerun` → Re-launch with same prompt

**Control:**
- `POST /api/pause` → Pause / resume new spawns
- `POST /api/interrupt/{agent_id}` → Interrupt one agent
- `GET /api/delegation/config` → Current delegation settings
- `POST /api/delegation/config` → Update max_concurrency, max_depth, etc.

**Observability:**
- `GET /api/stream` → SSE: live agent + mission + error events
- `GET /api/mission/{id}/events` → Get missed events (fallback for SSE reconnect)
- `GET /api/mission/{id}/metrics` → Per-mission metrics summary
- `GET /metrics` → Prometheus-format metrics (gauges, histograms, counters)

**Export & Analytics:**
- `GET /api/export` → Full ecosystem state as JSON
- `GET /api/missions/export` → CSV of all missions
- `GET /api/mission/{id}/download` → Compressed archive of one mission's logs

**Brain & Org:**
- `GET/POST /api/brain` → Agency knowledge store (gBRAIN) CRUD
- `GET/POST /api/org` → Org chart and specialist library CRUD
- `GET/POST /api/pods` → Client pod management

### 6.3 Dashboard UI Sections

| Section | Purpose | Update Freq | Primary Signal |
|---------|---------|-------------|-----------------|
| **Graph Canvas** | See swarm topology | SSE (50 ms) | Agent spawns/completions |
| **Activity Feed** | Recent events | SSE (100 ms) | All events |
| **Stats Strip** | Ecosystem health | 1−5 s | Counters, uptime |
| **Mission List** | Navigate missions | 500 ms | Status, progress |
| **Agent Drill-Down** | Details + logs | SSE (< 100 ms) | Tool calls, reasoning |
| **Control Panel** | Knobs + actions | Immediate | UI inputs → API calls |
| **Org Chart Tab** | Specialist registry | 5 s | Specialist assignment |
| **gBRAIN Drawer** | Knowledge entries | 5 s | On save |
| **Metrics Tab** | Analytics summary | 10 s | Aggregates |

---

## 7. Implementation Roadmap (Phased)

### Phase 1: Core Observability (MVP)
- ✅ Real-time agent graph (spawn → run → done)
- ✅ Activity feed (recent events)
- ✅ Stats strip (mission count, agents, uptime)
- ✅ Agent drill-down (tool activity log)
- ✅ Simple error highlighting
- **Timeline:** Weeks 1−2

### Phase 2: Operational Control
- Pause/resume spawning (UI knob → config change)
- Interrupt agent (button → API call)
- Cancel mission (button → API call)
- Concurrency tuning live
- **Timeline:** Weeks 3−4

### Phase 3: Analysis & Export
- Metrics dashboard (latency, success rate, cost per mission)
- JSON/CSV export
- Prometheus metrics scrape endpoint
- Historical trend charts
- **Timeline:** Weeks 5−6

### Phase 4: Advanced Features
- Org chart editor (live CRUD)
- gBRAIN knowledge entry CRUD
- Client pod management
- Undo/audit trail UI
- Specialist assignment override
- **Timeline:** Weeks 7−8

---

## 8. Success Metrics

**Operational Metrics:**
- Average time to identify failed agent: < 10 seconds (from error to drill-down view)
- Time to interrupt runaway agent: < 2 seconds (from click to confirmed interrupt)
- Dashboard uptime: > 99.9%
- SSE reconnect success rate: > 99%

**Product Metrics:**
- Ops team can manage 50+ concurrent agents without oversaturation
- Dashboard responds to scroll/clicks in < 200 ms (feels instant)
- Graph rendering smooth at 20+ agents; degradation graceful beyond

**Cost Metrics:**
- Dashboard server memory footprint: < 500 MB for 100 concurrent missions
- SSE event throughput: > 1000 events/second per client

---

## 9. Open Questions & Future Work

1. **Credential Rotation During Flight**
   - Can dashboard auto-detect and recover from expired API keys?
   - Trigger re-auth prompt in UI?

2. **Cost Attribution**
   - Should dashboard track per-agent API costs (based on token count)?
   - Expose cost per mission for billing?

3. **Multi-Zone / Distributed Agents**
   - How to handle agents spawned across different providers (anthropic vs. openai vs. local)?
   - Multi-region failover?

4. **Feedback Loop: Learning from Ops Decisions**
   - If ops interrupts an agent, should that be fed back to the Commander?
   - E.g., "This agent was interrupting too often; next time route to a different specialist"

5. **Agent Replay / Debugging**
   - Can ops replay an interrupted mission step-by-step, inspecting state at each agent?
   - Like a debugger for swarms?

---

## 10. References

- `hermes_hq/engine.py` — HQ Commander bootstrapping and mission execution
- `hermes_hq/server.py` — FastAPI app and SSE endpoints
- `tools/delegate_tool.py` — Agent spawning, concurrency, registry (`list_active_subagents()`)
- `hermes_hq/brain.py` — gBRAIN, org chart, pods persistence
- AGENTS.md — Core design principles (prompt caching, narrow waist)

---

**Document Status:** DRAFT  
**Approval Path:** Architecture Review → Ops Team Feedback → Eng Implementation  
**Last Updated:** June 13, 2026
