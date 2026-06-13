"""HQ engine -- bootstraps the lead Commander agent and runs missions.

This module owns the long-lived "HQ Commander" :class:`AIAgent` and the
machinery that runs a mission on a background thread while the web layer polls
the live subagent registry for visualisation.

Credential resolution reuses the *same* runtime-provider path the CLI and
``delegate_task`` use (``resolve_runtime_provider``), so HQ runs on whatever
provider/model the user has configured -- no duplicate config.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes_hq")


def _hq_state_dir() -> str:
    """Directory where HQ persists state, honouring HERMES_HOME / profiles.

    Resolved lazily (not at import) so tests pointing HERMES_HOME at a
    tempdir, and non-default profiles, write to the right place rather than
    the real ``~/.hermes``.
    """
    try:
        from hermes_constants import get_hermes_home

        base = str(get_hermes_home())
    except Exception:
        base = os.path.expanduser("~/.hermes")
    return os.path.join(base, "hermes_hq")


def _history_path() -> str:
    return os.path.join(_hq_state_dir(), "missions.json")


def _engine_live_subagents() -> List[Dict[str, Any]]:
    """Snapshot the core's live subagent registry (safe, returns [] on error)."""
    try:
        from tools.delegate_tool import list_active_subagents

        return list_active_subagents()
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Environment / credentials
# ---------------------------------------------------------------------------


def _load_env() -> None:
    """Load ``~/.hermes/.env`` so provider keys are visible in-process.

    The CLI does this at startup; when HQ runs standalone we must replicate it
    or ``resolve_runtime_provider`` cannot find the configured credentials.
    """
    try:
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - dotenv is a hard dep of the repo
        return
    for path in (
        os.path.join(os.path.expanduser("~/.hermes"), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ):
        if os.path.isfile(path):
            load_dotenv(path, override=False)


def resolve_hq_credentials(
    provider: Optional[str] = None, model: Optional[str] = None
) -> Dict[str, Any]:
    """Resolve a full credential bundle for the HQ Commander agent.

    Falls back to the user's configured default provider/model when not given.
    Raises ``RuntimeError`` with an actionable message on failure.
    """
    _load_env()
    from hermes_cli.runtime_provider import resolve_runtime_provider

    requested = provider or _configured_provider() or "auto"
    target_model = model or _configured_model() or None
    try:
        rt = resolve_runtime_provider(requested=requested, target_model=target_model)
    except Exception as exc:  # AuthError and friends
        raise RuntimeError(
            f"Could not resolve an inference provider for HERMES HQ: {exc}. "
            f"Run `hermes model` to configure a provider/model, or set a key "
            f"in ~/.hermes/.env."
        ) from exc
    if not rt.get("api_key") and not rt.get("command"):
        raise RuntimeError(
            f"Provider '{requested}' resolved but has no API key. "
            f"Run `hermes auth` or set the relevant *_API_KEY in ~/.hermes/.env."
        )
    rt.setdefault("model", target_model)
    return rt


def _configured_provider() -> Optional[str]:
    cfg = _load_user_config()
    mdl = cfg.get("model") or {}
    if isinstance(mdl, dict):
        return (mdl.get("provider") or "").strip() or None
    return None


def _configured_model() -> Optional[str]:
    cfg = _load_user_config()
    mdl = cfg.get("model") or {}
    if isinstance(mdl, dict):
        return (mdl.get("default") or "").strip() or None
    return None


def _load_user_config() -> Dict[str, Any]:
    try:
        import yaml

        path = os.path.join(os.path.expanduser("~/.hermes"), "config.yaml")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                return yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover
        logger.debug("config load failed: %s", exc)
    return {}


# ---------------------------------------------------------------------------
# Mission bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class Mission:
    """A single mission run by the HQ Commander."""

    id: str
    prompt: str
    status: str = "running"  # running | completed | failed | interrupted | cancelled
    pod: str = "default"  # client pod this mission belongs to (isolation)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    # Chronological log of high-level events for the activity feed.
    events: List[Dict[str, Any]] = field(default_factory=list)
    # Live token stream of the Commander's own reasoning/answer.
    commander_stream: str = ""
    # Per-mission metrics, updated as the run progresses.
    metrics: Dict[str, Any] = field(default_factory=lambda: {
        "subagents_spawned": 0,
        "subagent_tool_calls": 0,
        "peak_concurrency": 0,
        "max_depth": 1,
        # Token/cost accounting (delta of the Commander agent's session
        # counters across this mission's turn). 0 until the turn completes.
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
    })
    # Optional mission chaining: id of the mission whose result was fed into
    # this one's prompt as upstream context (None for un-chained missions).
    chained_from: Optional[str] = None
    # Set of subagent ids seen for this mission (for accurate counting).
    _seen_subagents: set = field(default_factory=set, repr=False)

    def duration(self) -> Optional[float]:
        if self.finished_at and (self.started_at or self.created_at):
            return self.finished_at - (self.started_at or self.created_at)
        return None

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "status": self.status,
            "pod": self.pod,
            "chained_from": self.chained_from,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration(),
            "result": self.result,
            "error": self.error,
            "events": self.events[-200:],
            "commander_stream": self.commander_stream[-8000:],
            "metrics": dict(self.metrics),
        }


@dataclass
class Schedule:
    """A recurring mission definition: fire ``prompt`` every ``interval`` secs.

    The scheduler thread checks due schedules and launches a normal mission
    for each. ``interval`` is in seconds (minimum enforced by the engine).
    """

    id: str
    prompt: str
    interval: float  # seconds between runs
    pod: str = "default"
    enabled: bool = True
    label: str = ""
    created_at: float = field(default_factory=time.time)
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    run_count: int = 0

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "interval": self.interval,
            "pod": self.pod,
            "enabled": self.enabled,
            "label": self.label,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
        }


# HQ Commander system prompt: instructs Hermes to behave as a delegating lead.
HQ_COMMANDER_PROMPT = """You are HERMES HQ COMMANDER, the lead agent of an autonomous multi-agent ecosystem — an "agent company" run inside an agency.

Your job is to take a mission and accomplish it by DELEGATING work to specialist
subagents using the `delegate_task` tool. You are an orchestrator first.

Operating doctrine:
- Decompose the mission into focused, independent sub-tasks.
- Route each sub-task to the right DEPARTMENT VERTICAL and SPECIALIST when the
  mission context lists them — name the vertical/specialist you are acting as in
  each subagent's goal so the work maps to the org chart.
- For independent sub-tasks, dispatch them IN PARALLEL in a single delegate_task
  call using the `tasks` array (up to the configured concurrency limit).
- Give each subagent a precise, self-contained goal and the context it needs
  (subagents have NO memory of this conversation).
- Pick the right toolsets per subagent (e.g. ['web'] for research,
  ['terminal','file'] for code, ['browser'] for web interaction).
- For a BROAD sub-task that itself splits into several independent pieces,
  delegate it with role='orchestrator' so that subagent can spawn its own
  workers (a nested swarm). Use role='leaf' (the default) for focused,
  self-contained tasks. Only orchestrators can sub-delegate, and only when
  the configured spawn depth allows it.
- HONOUR THE AGENCY BRAIN: when the mission context includes brain knowledge
  (voice, playbooks, conventions) or a CLIENT POD, apply it to every sub-task
  and keep each client pod's context isolated — never leak one client's details
  into another's work.
- When subagents return, synthesise their results into one clear final answer.
- Prefer delegation over doing the work yourself; you are the conductor.

Be decisive and move fast. Deliver a crisp final synthesis to the user."""


class SubagentMonitor:
    """Captures live per-subagent tool activity relayed by the delegate engine.

    The delegate progress callback relays ``subagent.*`` events up to the
    parent agent's ``tool_progress_callback`` with identity kwargs
    (``subagent_id``, ``parent_id``, ``depth``, ``model``, ``goal``,
    ``tool_count``). We capture those into a bounded per-subagent ring buffer
    so the dashboard can stream each agent's live output without any core
    changes -- this is the same event stream the TUI overlay consumes.
    """

    _MAX_LINES = 60

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # subagent_id -> {"goal","parent_id","depth","model","lines":[...]}
        self._buf: Dict[str, Dict[str, Any]] = {}

    def callback(
        self,
        event_type: Any,
        tool_name: Optional[str] = None,
        preview: Optional[str] = None,
        args: Any = None,
        **kwargs: Any,
    ) -> None:
        """Parent ``tool_progress_callback`` -- relayed subagent events land here."""
        try:
            sid = kwargs.get("subagent_id")
            if not sid:
                return
            with self._lock:
                rec = self._buf.setdefault(
                    sid,
                    {
                        "goal": kwargs.get("goal", ""),
                        "parent_id": kwargs.get("parent_id"),
                        "depth": kwargs.get("depth"),
                        "model": kwargs.get("model"),
                        "lines": [],
                    },
                )
                # keep identity fields fresh
                for k in ("goal", "parent_id", "depth", "model"):
                    if kwargs.get(k) is not None:
                        rec[k] = kwargs.get(k)

                ev = str(getattr(event_type, "value", event_type) or "")
                line = self._format_line(ev, tool_name, preview, kwargs)
                if line:
                    rec["lines"].append({"t": time.time(), "text": line, "ev": ev})
                    if len(rec["lines"]) > self._MAX_LINES:
                        rec["lines"] = rec["lines"][-self._MAX_LINES :]
        except Exception as exc:  # never let telemetry break a run
            logger.debug("SubagentMonitor callback error: %s", exc)

    @staticmethod
    def _format_line(
        ev: str, tool_name: Optional[str], preview: Optional[str], kwargs: Dict[str, Any]
    ) -> str:
        prev = (preview or "").strip().replace("\n", " ")
        if len(prev) > 160:
            prev = prev[:160] + "…"
        if ev in ("subagent.start", "subagent_start"):
            return f"▶ started: {prev or kwargs.get('goal','')}"
        if ev in ("subagent.tool", "subagent_tool"):
            t = tool_name or "tool"
            return f"⚙ {t}" + (f"  {prev}" if prev else "")
        if ev in ("subagent.thinking", "subagent_thinking"):
            return f"💭 {prev}" if prev else ""
        if ev in ("subagent.progress", "subagent_progress"):
            return f"… {prev}" if prev else ""
        if ev in ("subagent.complete", "subagent_complete"):
            return f"✓ complete{(': ' + prev) if prev else ''}"
        return ""

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                sid: {
                    "goal": rec.get("goal", ""),
                    "parent_id": rec.get("parent_id"),
                    "depth": rec.get("depth"),
                    "model": rec.get("model"),
                    "lines": list(rec.get("lines", []))[-self._MAX_LINES :],
                }
                for sid, rec in self._buf.items()
            }

    def lines_for(self, subagent_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rec = self._buf.get(subagent_id)
            return list(rec.get("lines", [])) if rec else []


class HQEngine:
    """Owns the HQ Commander agent and runs missions on background threads."""

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self._provider = provider
        self._model = model
        self._agent = None
        self._agent_lock = threading.Lock()
        self._missions: Dict[str, Mission] = {}
        self._missions_lock = threading.Lock()
        # HQ uses ONE long-lived Commander agent whose state (token counters,
        # interrupt flag, todo store, session persistence) is shared. Concurrent
        # turns on it would corrupt each other, so missions queue and run one at
        # a time through this lock; `_active_mission_id` is the one currently
        # holding it (used to route cancel/interrupt to the right mission).
        self._run_lock = threading.Lock()
        self._active_mission_id: Optional[str] = None
        self._creds: Dict[str, Any] = {}
        # Readiness probe state: whether the configured provider/model resolves
        # to usable credentials, independent of whether the (lazy) Commander
        # agent has been built yet. Lets /api/info report the real provider/model
        # and an accurate status before the first mission runs.
        self._ready: Optional[bool] = None
        self._ready_error: Optional[str] = None
        self._probe_lock = threading.Lock()
        self.monitor = SubagentMonitor()
        # The agency brain: shared knowledge, org chart, client pods.
        from hermes_hq.brain import HQBrain
        self.brain = HQBrain()

        # Opportunity Assistant: approval-gated income-research/draft queue.
        # Agents only research + draft; nothing touching money or outbound
        # executes without explicit human approval (see opportunities.py).
        from hermes_hq.opportunities import OpportunityQueue
        self.opportunities = OpportunityQueue()
        
        # Self-improvement and adaptive systems
        from hermes_hq.self_improvement import (
            AgentLearningEngine,
            AgentEvolutionManager,
        )
        from hermes_hq.performance import (
            PerformanceAnalyzer,
            OptimizationEngine,
            ExperienceCollector,
        )
        from hermes_hq.adaptive import (
            CapabilityManager,
            RuntimeAdaptationEngine,
            PersonaGenerator,
        )
        
        self.learning_engine = AgentLearningEngine()
        self.evolution_manager = AgentEvolutionManager(self.learning_engine)
        self.performance_analyzer = PerformanceAnalyzer()
        self.optimization_engine = OptimizationEngine()
        self.experience_collector = ExperienceCollector()
        self.capability_manager = CapabilityManager()
        self.adaptation_engine = RuntimeAdaptationEngine()
        self.persona_generator = PersonaGenerator()
        
        # Map a running agent thread -> Mission, so the monitor callback can
        # attribute subagent activity to the right mission for live metrics.
        self._thread_mission: Dict[int, Mission] = {}
        self._started_at = time.time()
        # Resolve the persistence paths once so a single engine instance is stable.
        self._history_path = _history_path()
        self._schedules_path = os.path.join(_hq_state_dir(), "schedules.json")
        # Recurring-mission schedules + a daemon scheduler loop.
        self._schedules: Dict[str, Schedule] = {}
        self._schedules_lock = threading.Lock()
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None
        self._load_history()
        self._load_schedules()
        self._start_scheduler()

    # -- scheduler ----------------------------------------------------------

    _MIN_INTERVAL = 30.0  # floor so a misconfigured schedule can't hammer

    def _load_schedules(self) -> None:
        try:
            if not os.path.isfile(self._schedules_path):
                return
            with open(self._schedules_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for rec in data.get("schedules", []):
                try:
                    s = Schedule(
                        id=rec.get("id") or uuid.uuid4().hex[:12],
                        prompt=rec.get("prompt", ""),
                        interval=max(self._MIN_INTERVAL, float(rec.get("interval", 3600))),
                        pod=rec.get("pod", "default"),
                        enabled=bool(rec.get("enabled", True)),
                        label=rec.get("label", ""),
                        created_at=rec.get("created_at", time.time()),
                        last_run=rec.get("last_run"),
                        run_count=int(rec.get("run_count", 0) or 0),
                    )
                    # Schedule the next run relative to now so a long downtime
                    # doesn't trigger a burst of immediate catch-up runs.
                    s.next_run = time.time() + s.interval
                    self._schedules[s.id] = s
                except Exception:
                    continue
        except Exception as exc:  # pragma: no cover
            logger.debug("schedules load failed: %s", exc)

    def _save_schedules(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._schedules_path), exist_ok=True)
            with self._schedules_lock:
                recs = [s.to_public() for s in self._schedules.values()]
            tmp = self._schedules_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"schedules": recs}, fh, default=str)
            os.replace(tmp, self._schedules_path)
        except Exception as exc:  # pragma: no cover
            logger.debug("schedules save failed: %s", exc)

    def _start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True, name="hq-scheduler"
        )
        self._scheduler_thread.start()

    def _scheduler_loop(self) -> None:
        """Fire due schedules. Runs every few seconds until stopped."""
        while not self._scheduler_stop.wait(5.0):
            try:
                self.tick_schedules()
            except Exception as exc:  # never let the loop die
                logger.debug("scheduler tick failed: %s", exc)

    def tick_schedules(self, now: Optional[float] = None) -> List[str]:
        """Launch any schedule whose ``next_run`` has passed. Returns fired ids.

        Exposed (not just internal) so tests can drive it deterministically
        without waiting on the timer thread.
        """
        now = now if now is not None else time.time()
        fired: List[str] = []
        with self._schedules_lock:
            due = [
                s for s in self._schedules.values()
                if s.enabled and (s.next_run is None or s.next_run <= now)
            ]
        for s in due:
            try:
                self.start_mission(s.prompt, pod=s.pod)
                s.last_run = now
                s.run_count += 1
                s.next_run = now + s.interval
                fired.append(s.id)
            except Exception as exc:
                logger.debug("schedule %s failed to fire: %s", s.id, exc)
        if fired:
            self._save_schedules()
        return fired

    def list_schedules(self) -> List[Dict[str, Any]]:
        with self._schedules_lock:
            return [s.to_public() for s in self._schedules.values()]

    def add_schedule(self, prompt: str, interval: float, pod: str = "default",
                     label: str = "") -> Schedule:
        s = Schedule(
            id=uuid.uuid4().hex[:12],
            prompt=(prompt or "").strip(),
            interval=max(self._MIN_INTERVAL, float(interval)),
            pod=pod or "default",
            label=(label or "").strip(),
        )
        s.next_run = time.time() + s.interval
        with self._schedules_lock:
            self._schedules[s.id] = s
        self._save_schedules()
        return s

    def set_schedule_enabled(self, schedule_id: str, enabled: bool) -> bool:
        with self._schedules_lock:
            s = self._schedules.get(schedule_id)
            if not s:
                return False
            s.enabled = bool(enabled)
            if s.enabled and s.next_run is None:
                s.next_run = time.time() + s.interval
        self._save_schedules()
        return True

    def delete_schedule(self, schedule_id: str) -> bool:
        with self._schedules_lock:
            existed = schedule_id in self._schedules
            self._schedules.pop(schedule_id, None)
        if existed:
            self._save_schedules()
        return existed

    # -- persistence --------------------------------------------------------

    def _load_history(self) -> None:
        """Load past missions from disk so history survives app restarts."""
        history_path = self._history_path
        try:
            if not os.path.isfile(history_path):
                return
            with open(history_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for rec in data.get("missions", [])[-200:]:
                m = Mission(
                    id=rec.get("id") or uuid.uuid4().hex[:12],
                    prompt=rec.get("prompt", ""),
                    status=rec.get("status", "completed"),
                    pod=rec.get("pod", "default"),
                    chained_from=rec.get("chained_from"),
                    created_at=rec.get("created_at", time.time()),
                    started_at=rec.get("started_at"),
                    finished_at=rec.get("finished_at"),
                    result=rec.get("result"),
                    error=rec.get("error"),
                    events=rec.get("events", []),
                    commander_stream=rec.get("commander_stream", ""),
                    metrics=rec.get("metrics", {}) or {},
                )
                # A mission that was "running" when the app died is stale.
                if m.status == "running":
                    m.status = "interrupted"
                    m.finished_at = m.finished_at or time.time()
                self._missions[m.id] = m
            logger.info("loaded %d past missions from history", len(self._missions))
        except Exception as exc:  # pragma: no cover
            logger.debug("history load failed: %s", exc)

    def _save_history(self) -> None:
        """Persist mission history (best-effort, atomic)."""
        history_path = self._history_path
        try:
            os.makedirs(os.path.dirname(history_path), exist_ok=True)
            with self._missions_lock:
                recs = [m.to_public() for m in self._missions.values()]
            recs.sort(key=lambda r: r.get("created_at") or 0)
            tmp = history_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"missions": recs[-200:]}, fh, default=str)
            os.replace(tmp, history_path)
        except Exception as exc:  # pragma: no cover
            logger.debug("history save failed: %s", exc)

    # -- agent lifecycle ----------------------------------------------------

    def ensure_agent(self):
        """Lazily build the long-lived HQ Commander agent (thread-safe)."""
        with self._agent_lock:
            if self._agent is not None:
                return self._agent
            creds = resolve_hq_credentials(self._provider, self._model)
            self._creds = creds
            from run_agent import AIAgent

            model = creds.get("model") or self._model or ""
            self._agent = AIAgent(
                base_url=creds.get("base_url"),
                api_key=creds.get("api_key"),
                provider=creds.get("provider"),
                api_mode=creds.get("api_mode"),
                command=creds.get("command"),
                args=creds.get("args") or None,
                model=model,
                quiet_mode=True,
                skip_memory=True,
                skip_context_files=True,
                ephemeral_system_prompt=HQ_COMMANDER_PROMPT,
                tool_progress_callback=self._monitor_callback,
            )
            self._ready, self._ready_error = True, None
            logger.info(
                "HQ Commander online: provider=%s model=%s",
                creds.get("provider"),
                model or "(provider default)",
            )
            return self._agent

    def _probe(self) -> None:
        """Resolve credentials without building the agent, so /api/info can
        report the real provider/model and readiness before any mission runs.

        Success is cached permanently; failure is re-probed on each call so a
        fixed config/key is reflected without restarting the server.
        """
        with self._probe_lock:
            if self._ready and self._creds:
                return
            try:
                self._creds = resolve_hq_credentials(self._provider, self._model)
                self._ready, self._ready_error = True, None
            except Exception as exc:
                self._ready, self._ready_error = False, str(exc)

    def info(self) -> Dict[str, Any]:
        if self._ready is None or not self._creds:
            self._probe()
        creds = self._creds or {}
        return {
            "provider": creds.get("provider") or self._provider or "(auto)",
            "model": creds.get("model") or self._model or "(default)",
            # online: the Commander agent is built and live in this process.
            "online": self._agent is not None,
            # ready: credentials resolve, so HQ can run a mission on demand.
            "ready": bool(self._ready),
            "error": self._ready_error,
        }

    def stats(self) -> Dict[str, Any]:
        """Aggregate ecosystem stats across all missions for the dashboard."""
        with self._missions_lock:
            missions = list(self._missions.values())
        total = len(missions)
        by_status: Dict[str, int] = {}
        total_subagents = 0
        total_tools = 0
        total_duration = 0.0
        total_tokens = 0
        total_cost = 0.0
        durations: List[float] = []
        for m in missions:
            by_status[m.status] = by_status.get(m.status, 0) + 1
            total_subagents += int(m.metrics.get("subagents_spawned", 0) or 0)
            total_tools += int(m.metrics.get("subagent_tool_calls", 0) or 0)
            total_tokens += int(m.metrics.get("total_tokens", 0) or 0)
            total_cost += float(m.metrics.get("cost_usd", 0.0) or 0.0)
            d = m.duration()
            if d:
                durations.append(d)
                total_duration += d
        running = by_status.get("running", 0)
        completed = by_status.get("completed", 0)
        succ_rate = (completed / total * 100.0) if total else 0.0
        return {
            "uptime": time.time() - self._started_at,
            "missions_total": total,
            "missions_running": running,
            "missions_completed": completed,
            "by_status": by_status,
            "subagents_total": total_subagents,
            "tool_calls_total": total_tools,
            "tokens_total": total_tokens,
            "cost_total": round(total_cost, 4),
            "success_rate": round(succ_rate, 1),
            "avg_duration": round(total_duration / len(durations), 1) if durations else 0.0,
            "active_subagents": len(_engine_live_subagents()),
        }

    # -- mission control ----------------------------------------------------

    def pod_analytics(self) -> List[Dict[str, Any]]:
        """Per-pod aggregate metrics for the analytics view.

        Rolls every mission up by its pod so the dashboard can compare clients:
        mission counts by status, success rate, total subagents/tool calls,
        tokens, cost, and average duration. Includes pods with zero missions
        (so freshly-created clients still show a row), keyed by the live pod
        list from the brain.
        """
        with self._missions_lock:
            missions = list(self._missions.values())
        # Seed rows from known pods so empty pods appear too.
        rows: Dict[str, Dict[str, Any]] = {}
        try:
            pods = self.brain.list_pods()
        except Exception:
            pods = []
        name_by_id = {p.get("id"): p.get("name") for p in pods}
        for p in pods:
            rows[p.get("id")] = self._empty_pod_row(p.get("id"), p.get("name"))
        for m in missions:
            pid = m.pod or "default"
            row = rows.get(pid)
            if row is None:
                row = self._empty_pod_row(pid, name_by_id.get(pid, pid))
                rows[pid] = row
            row["missions"] += 1
            row["by_status"][m.status] = row["by_status"].get(m.status, 0) + 1
            if m.status == "completed":
                row["completed"] += 1
            row["subagents"] += int(m.metrics.get("subagents_spawned", 0) or 0)
            row["tool_calls"] += int(m.metrics.get("subagent_tool_calls", 0) or 0)
            row["tokens"] += int(m.metrics.get("total_tokens", 0) or 0)
            row["cost_usd"] += float(m.metrics.get("cost_usd", 0.0) or 0.0)
            d = m.duration()
            if d:
                row["_durations"].append(d)
        out: List[Dict[str, Any]] = []
        for row in rows.values():
            durs = row.pop("_durations")
            row["avg_duration"] = round(sum(durs) / len(durs), 1) if durs else 0.0
            row["success_rate"] = (
                round(row["completed"] / row["missions"] * 100.0, 1) if row["missions"] else 0.0
            )
            row["cost_usd"] = round(row["cost_usd"], 4)
            out.append(row)
        # Busiest pods first, default agency last as a tiebreaker.
        out.sort(key=lambda r: (-r["missions"], r["id"] == "default"))
        return out

    @staticmethod
    def _empty_pod_row(pod_id: Optional[str], name: Optional[str]) -> Dict[str, Any]:
        return {
            "id": pod_id or "default",
            "name": name or pod_id or "default",
            "missions": 0,
            "completed": 0,
            "by_status": {},
            "subagents": 0,
            "tool_calls": 0,
            "tokens": 0,
            "cost_usd": 0.0,
            "_durations": [],
        }

    # -- mission lifecycle --------------------------------------------------

    def cancel_mission(self, mission_id: str) -> bool:
        """Cancel a running or queued mission.

        Only the mission currently holding the shared Commander is interrupted;
        a mission still queued behind it is marked cancelled in place and simply
        never starts (interrupting the agent would abort the *active* mission,
        not this one).
        """
        with self._missions_lock:
            m = self._missions.get(mission_id)
            is_active = self._active_mission_id == mission_id
        if not m or m.status != "running":
            return False
        if is_active:
            agent = self._agent
            if agent is not None and hasattr(agent, "interrupt"):
                try:
                    agent.interrupt("Mission cancelled by operator from HERMES HQ.")
                except Exception as exc:  # noqa: BLE001
                    logger.debug("interrupt failed: %s", exc)
        m.status = "cancelled"
        self._log_event(m, "error", "Mission cancelled by operator")
        return True

    def delete_mission(self, mission_id: str) -> bool:
        with self._missions_lock:
            existed = mission_id in self._missions
            self._missions.pop(mission_id, None)
        if existed:
            self._save_history()
        return existed

    def clear_history(self) -> int:
        """Remove all finished missions; keep running ones."""
        with self._missions_lock:
            keep = {k: v for k, v in self._missions.items() if v.status == "running"}
            removed = len(self._missions) - len(keep)
            self._missions = keep
        self._save_history()
        return removed

    def _monitor_callback(self, event_type: Any, tool_name: Optional[str] = None,
                          preview: Optional[str] = None, args: Any = None,
                          **kwargs: Any) -> None:
        """Wrap the SubagentMonitor callback to also update live mission metrics.

        Subagent events are emitted on the Commander's execution thread, so we
        look up which mission owns the current thread and fold the activity into
        its metrics (spawned count, tool calls, peak concurrency, max depth).
        """
        # Always feed the visual monitor first (never let metrics break it).
        try:
            self.monitor.callback(event_type, tool_name, preview, args, **kwargs)
        except Exception:
            pass
        try:
            mission = self._thread_mission.get(threading.get_ident())
            if not mission:
                return
            ev = str(getattr(event_type, "value", event_type) or "")
            sid = kwargs.get("subagent_id")
            met = mission.metrics
            if sid and sid not in mission._seen_subagents:
                mission._seen_subagents.add(sid)
                met["subagents_spawned"] = met.get("subagents_spawned", 0) + 1
            if "tool" in ev:
                met["subagent_tool_calls"] = met.get("subagent_tool_calls", 0) + 1
            depth = kwargs.get("depth")
            if isinstance(depth, int):
                met["max_depth"] = max(met.get("max_depth", 1), depth)
            live = len(_engine_live_subagents())
            met["peak_concurrency"] = max(met.get("peak_concurrency", 0), live)
        except Exception as exc:  # never let telemetry break a run
            logger.debug("metric update failed: %s", exc)

    # -- missions -----------------------------------------------------------

    def list_missions(self, pod: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._missions_lock:
            missions = list(self._missions.values())
        if pod:
            missions = [m for m in missions if m.pod == pod]
        return [m.to_public() for m in missions]

    def get_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        with self._missions_lock:
            m = self._missions.get(mission_id)
            return m.to_public() if m else None

    def start_mission(self, prompt: str, pod: str = "default",
                      chained_from: Optional[str] = None) -> Mission:
        """Kick off a mission on a background thread and return immediately.

        When ``chained_from`` names a finished mission, that mission's result
        is composed into this mission's prompt as upstream context (mission
        chaining) so the Commander builds on the prior output.
        """
        eff_prompt = prompt
        if chained_from:
            with self._missions_lock:
                src = self._missions.get(chained_from)
            if src and (src.result or "").strip():
                eff_prompt = (
                    "# UPSTREAM RESULT (from a prior mission — build on this)\n"
                    f"Prior mission prompt: {src.prompt}\n\n"
                    f"Prior mission result:\n{src.result}\n\n"
                    "# THIS MISSION\n"
                    f"{prompt}"
                )
        mission = Mission(id=uuid.uuid4().hex[:12], prompt=eff_prompt, pod=pod or "default",
                          chained_from=chained_from)
        with self._missions_lock:
            self._missions[mission.id] = mission
        t = threading.Thread(
            target=self._run_mission, args=(mission,), daemon=True, name=f"hq-{mission.id}"
        )
        t.start()
        return mission

    def rerun_mission(self, mission_id: str) -> Optional[Mission]:
        """Re-launch an existing mission's prompt as a brand-new mission."""
        with self._missions_lock:
            src = self._missions.get(mission_id)
        if not src:
            return None
        return self.start_mission(src.prompt, pod=src.pod)

    def shutdown(self) -> None:
        """Flush state for a graceful stop: interrupt running missions, save."""
        try:
            self._scheduler_stop.set()
        except Exception:
            pass
        agent = self._agent
        if agent is not None and hasattr(agent, "interrupt"):
            try:
                agent.interrupt("HERMES HQ shutting down.")
            except Exception:
                pass
        try:
            self._save_history()
        except Exception:
            pass

    def _log_event(self, mission: Mission, kind: str, message: str, **extra: Any) -> None:
        mission.events.append(
            {"t": time.time(), "kind": kind, "message": message, **extra}
        )

    def _record_usage(self, mission: Mission, agent: Any, pre: Dict[str, Any]) -> None:
        """Fold the post-turn token/cost delta into the mission metrics.

        ``pre`` is the snapshot taken before the turn; we subtract it from the
        current counters so each mission records only its own spend even though
        the Commander agent is shared and its counters are cumulative.
        """
        try:
            post = _token_snapshot(agent)
            met = mission.metrics
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                delta = int(post.get(key, 0)) - int(pre.get(key, 0))
                met[key] = max(0, delta)
            cost_delta = float(post.get("cost_usd", 0.0)) - float(pre.get("cost_usd", 0.0))
            met["cost_usd"] = round(max(0.0, cost_delta), 6)
        except Exception as exc:  # never let accounting break a run
            logger.debug("usage record failed: %s", exc)

    def _run_mission(self, mission: Mission) -> None:
        self._thread_mission[threading.get_ident()] = mission
        try:
            agent = self.ensure_agent()
            # Serialize Commander turns on the shared agent (see _run_lock).
            # A mission launched while another is running waits here rather than
            # racing on shared agent state.
            if not self._run_lock.acquire(blocking=False):
                self._log_event(mission, "commander",
                                "Queued — waiting for the Commander to free up")
                self._run_lock.acquire()
            try:
                # A mission cancelled while still queued must never start.
                if mission.status == "cancelled":
                    mission.started_at = mission.started_at or time.time()
                    self._log_event(mission, "mission_done",
                                    "Mission stopped (cancelled before start)")
                    return
                with self._missions_lock:
                    self._active_mission_id = mission.id
                mission.started_at = time.time()
                self._log_event(mission, "mission_start",
                                "HQ Commander received mission")
                # The Commander runs a full agent turn; it autonomously calls
                # delegate_task to fan work out to subagents. We run it as a
                # single user message and capture the final assistant text.
                result_text = self._run_agent_turn(agent, mission)
                mission.result = result_text
                # Respect a cancel that landed mid-run.
                if mission.status != "cancelled":
                    mission.status = "completed"
                    self._log_event(mission, "mission_done", "Mission complete")
                    # Opt-in opportunity capture: if this mission was tagged as
                    # an opportunity scan, file its result into the approval-
                    # gated queue as a DRAFT pending human review. Never auto-
                    # approves; never executes anything outbound.
                    try:
                        self._maybe_capture_opportunity(mission)
                    except Exception as exc:  # never let capture break a run
                        logger.debug("opportunity capture failed: %s", exc)
                else:
                    self._log_event(mission, "mission_done", "Mission stopped (cancelled)")
            finally:
                with self._missions_lock:
                    if self._active_mission_id == mission.id:
                        self._active_mission_id = None
                self._run_lock.release()
        except Exception as exc:  # noqa: BLE001 - surface any failure to UI
            logger.exception("Mission %s failed", mission.id)
            if mission.status != "cancelled":
                mission.status = "failed"
                mission.error = str(exc)
                self._log_event(mission, "error", f"Mission failed: {exc}")
        finally:
            mission.finished_at = time.time()
            self._thread_mission.pop(threading.get_ident(), None)
            # Record the REAL mission outcome into the learning engine so agent
            # stats reflect actual runs (cost, tokens, duration, success) — not
            # demo data. Never let telemetry break a mission.
            try:
                self._record_learning_outcome(mission)
            except Exception as exc:
                logger.debug("learning outcome record failed: %s", exc)
            self._save_history()

    def _run_agent_turn(self, agent, mission: Mission) -> str:
        """Run one HQ Commander turn and return its final text answer.

        Streams the Commander's own tokens into ``mission.commander_stream``
        live (via ``chat(message, stream_callback=...)``) so the dashboard
        shows the lead agent reasoning in real time, then returns the final
        synthesised answer.

        The agency brain + org chart + (optional) client-pod knowledge are
        composed into the USER message — NOT the system prompt — so the
        Commander's cached system-prompt prefix stays byte-stable across
        missions (prompt caching is sacred) while each mission still gets the
        right, possibly pod-isolated, context.
        """
        # Compose the brain context for this mission's pod and prepend it to the
        # mission prompt as a context block the Commander reads before acting.
        try:
            ctx = self.brain.compose_context(mission.pod)
        except Exception as exc:  # never let brain composition break a run
            logger.debug("brain compose failed: %s", exc)
            ctx = ""
        if ctx:
            prompt = (
                "# ECOSYSTEM CONTEXT (agency brain / org / client pod)\n"
                f"{ctx}\n\n"
                "# MISSION\n"
                f"{mission.prompt}"
            )
            self._log_event(mission, "commander",
                            f"Loaded brain context (pod={mission.pod})")
        else:
            prompt = mission.prompt

        def _on_token(tok: Any) -> None:
            try:
                if tok:
                    mission.commander_stream += str(tok)
            except Exception:
                pass

        # Snapshot the Commander's cumulative session token/cost counters so we
        # can record the per-mission delta after the turn. HQ uses one
        # long-lived agent, so before/after deltas isolate this mission's spend.
        pre = _token_snapshot(agent)
        # Prefer run_conversation() over the thin chat() wrapper: it returns the
        # full result dict, including the `error` the core sets when the model
        # call fails (billing/auth/HTTP 4xx). chat() returns only
        # `final_response`, so a failed turn yields an empty string and the
        # mission would be silently marked "completed" with no result. We surface
        # those failures by raising, so _run_mission marks the mission failed.
        run_conv = getattr(agent, "run_conversation", None)
        if callable(run_conv):
            self._log_event(mission, "commander", "Commander reasoning (agentic loop)")
            try:
                res = run_conv(prompt, stream_callback=_on_token)
            except TypeError:
                # Older signature without stream_callback.
                res = run_conv(prompt)
            self._record_usage(mission, agent, pre)
            return self._finalize_turn(mission, res)
        # Fallback to chat() if run_conversation is ever renamed.
        chat = getattr(agent, "chat", None)
        if callable(chat):
            self._log_event(mission, "commander", "Commander reasoning (chat)")
            try:
                out = chat(prompt, stream_callback=_on_token)
            except TypeError:
                out = chat(prompt)
            self._record_usage(mission, agent, pre)
            return self._finalize_turn(mission, out)
        raise RuntimeError(
            "HQ Commander agent exposes no known run method "
            "(tried run_conversation/chat)."
        )

    def _finalize_turn(self, mission: Mission, res: Any) -> str:
        """Extract the Commander's answer, raising if the turn actually failed.

        The core's run_conversation returns ``{"final_response": ..., "error":
        ...}``; a non-retryable model failure (e.g. billing/auth) sets ``error``
        and a ``None`` final_response. We raise on that so the mission is marked
        ``failed`` with the provider's message — never silently "completed".
        """
        if isinstance(res, dict):
            err = res.get("error")
            if err:
                raise RuntimeError(str(err))
            text = _stringify_agent_output(res.get("final_response"))
        else:
            text = _stringify_agent_output(res)
        # An empty answer with no delegation means the turn produced nothing —
        # usually a swallowed model/transport failure. Don't pass it off as done.
        if not text.strip() and not mission.metrics.get("subagents_spawned"):
            raise RuntimeError(
                "HQ Commander produced no output and dispatched no subagents — "
                "the underlying model call likely failed (check provider "
                "credits, credentials, and model)."
            )
        return text

    # -- opportunity capture (approval-gated) -------------------------------

    # Missions whose prompt contains this tag are treated as opportunity scans:
    # their result is filed into the OpportunityQueue as a DRAFT for review.
    OPPORTUNITY_TAG = "[OPPORTUNITY]"

    def _maybe_capture_opportunity(self, mission: Mission) -> None:
        """File a completed opportunity-scan mission into the approval queue.

        Only fires when the mission prompt is explicitly tagged with
        OPPORTUNITY_TAG, so normal missions are never captured. The captured
        item is created as a DRAFT and immediately submitted for human review —
        it can NEVER reach `approved` without an explicit human action, and
        nothing outbound/financial is executed here.
        """
        prompt = mission.prompt or ""
        if self.OPPORTUNITY_TAG not in prompt:
            return
        result = (mission.result or "").strip()
        if not result:
            return
        # Derive a concise title from the mission prompt (sans the tag).
        title = prompt.replace(self.OPPORTUNITY_TAG, "").strip()
        title = (title.splitlines()[0] if title else "Opportunity")[:120] or "Opportunity"
        opp = self.opportunities.add(
            title=title,
            category="research",
            summary=result[:2000],
            source=f"mission:{mission.id}",
            draft=result,
            # The Commander is instructed (in the mission prompt template) to end
            # with a "PROPOSED NEXT STEP:" line; we surface the whole result as
            # the draft and let risk classification gate the action text.
            proposed_action=self._extract_proposed_action(result),
            mission_id=mission.id,
            pod=mission.pod,
        )
        # Surface for review immediately; humans decide from here.
        self.opportunities.submit_for_review(opp.id, note="auto-captured from mission")
        self._log_event(
            mission, "opportunity",
            f"Captured opportunity {opp.id} for review "
            f"(requires_approval={opp.requires_approval})",
        )

    @staticmethod
    def _extract_proposed_action(result_text: str) -> str:
        """Pull the 'PROPOSED NEXT STEP:' line out of a Commander result, if any.

        Falls back to empty (which classify_risk treats as 'no action described'
        -> not auto-gated, but still only a draft). The point is to feed the risk
        classifier the actual action so outbound/money steps get flagged.
        """
        for line in (result_text or "").splitlines():
            low = line.strip().lower()
            if low.startswith("proposed next step") or low.startswith("next step"):
                return line.split(":", 1)[-1].strip() if ":" in line else line.strip()
        return ""

    # -- real learning outcome recording ------------------------------------

    def _record_learning_outcome(self, mission: Mission) -> None:
        """Feed a finished mission's REAL data into the learning engine.

        This is the bridge that makes agent stats reflect reality. Everything
        recorded here comes from the mission's actual run — no synthetic values:
          - success  := mission.status == "completed"
          - duration := mission.duration() (real wall-clock)
          - metrics  := the real token/cost/subagent counters the core reported
          - learned_items := the mission's pod (the work category) — an honest,
            observable label, NOT a fabricated skill name.

        A cancelled mission is skipped: it isn't a real performance signal.
        """
        if mission.status == "cancelled":
            return
        m = mission.metrics or {}
        # The HQ Commander is the agent that runs every mission. Attribute the
        # outcome to it, keyed by the live model so stats are per-Commander-model.
        info = {}
        try:
            info = self.info() or {}
        except Exception:
            pass
        model = (info.get("model") or self._model or "unknown")
        agent_id = f"commander:{model}"
        success = (mission.status == "completed")
        duration = mission.duration() or 0.0
        metrics = {
            "cost_usd": float(m.get("cost_usd", 0.0) or 0.0),
            "total_tokens": float(m.get("total_tokens", 0) or 0),
            "input_tokens": float(m.get("input_tokens", 0) or 0),
            "output_tokens": float(m.get("output_tokens", 0) or 0),
            "subagents_spawned": float(m.get("subagents_spawned", 0) or 0),
        }
        # Honest "skill" label: the pod the mission ran in (its work category).
        # This is observed, not invented.
        learned = [f"pod:{mission.pod}"] if mission.pod else []
        self.learning_engine.record_mission_outcome(
            agent_id=agent_id,
            mission_id=mission.id,
            agent_type="commander",
            duration=float(duration),
            success=success,
            subagent_count=int(m.get("subagents_spawned", 0) or 0),
            metrics=metrics,
            learned_items=learned,
            failure_reason=(mission.error if not success else None),
        )


def _token_snapshot(agent: Any) -> Dict[str, Any]:
    """Snapshot the agent's cumulative session token/cost counters.

    Returns zeros for any counter the agent doesn't expose so callers can
    always diff safely. HQ uses these to derive per-mission deltas.
    """
    def _g(name: str, default: Any = 0) -> Any:
        try:
            return getattr(agent, name, default)
        except Exception:
            return default

    return {
        "input_tokens": _g("session_input_tokens", 0) or 0,
        "output_tokens": _g("session_output_tokens", 0) or 0,
        "total_tokens": _g("session_total_tokens", 0) or 0,
        "cost_usd": float(_g("session_estimated_cost_usd", 0.0) or 0.0),
    }


def _stringify_agent_output(out: Any) -> str:
    if out is None:
        return ""
    if isinstance(out, str):
        return out
    if isinstance(out, dict):
        for key in ("content", "text", "message", "final", "response"):
            val = out.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return str(out)
    return str(out)
