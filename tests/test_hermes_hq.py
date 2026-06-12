"""Tests for the HERMES HQ edge app (brain, engine, server wiring).

These exercise the real modules against an isolated ``HERMES_HOME`` (provided
by the suite-wide conftest fixture) so persistence writes to a tempdir, never
the developer's real ``~/.hermes``. They assert *behavior contracts* — how the
pieces relate — rather than snapshotting mutable data like default catalogs.

The Commander agent itself is never built here (that needs a live provider);
we test the bookkeeping, brain composition, scheduling, chaining, analytics,
and accounting that surround it, plus that the FastAPI app wires every route.
"""

from __future__ import annotations

import importlib
import time

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_brain():
    """A brain bound to the per-test HERMES_HOME tempdir."""
    brain = importlib.import_module("hermes_hq.brain")
    return brain.HQBrain()


def _fresh_engine():
    """An engine that doesn't build a live agent (we never call ensure_agent)."""
    engine_mod = importlib.import_module("hermes_hq.engine")
    return engine_mod.HQEngine()


# ---------------------------------------------------------------------------
# Persistence honours HERMES_HOME (no writes to the real ~/.hermes)
# ---------------------------------------------------------------------------


def test_brain_persists_under_hermes_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    brain = _fresh_brain()
    # The store path must be inside the isolated home, not the real one.
    assert str(tmp_path) in brain._path
    assert brain._path.endswith("gbrain.json")


def test_engine_history_path_under_hermes_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine = _fresh_engine()
    assert str(tmp_path) in engine._history_path
    assert str(tmp_path) in engine._schedules_path


# ---------------------------------------------------------------------------
# gBRAIN: knowledge entries, org chart, library, pods
# ---------------------------------------------------------------------------


def test_brain_entry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    brain = _fresh_brain()
    e = brain.add_brain_entry("Voice", "Be concise.", tags=["style"])
    assert e["id"] in {x["id"] for x in brain.list_brain()}
    # A fresh instance must reload the same entry from disk (persistence).
    brain2 = _fresh_brain()
    assert any(x["title"] == "Voice" for x in brain2.list_brain())
    assert brain.delete_brain_entry(e["id"]) is True
    assert e["id"] not in {x["id"] for x in brain.list_brain()}


def test_default_pod_cannot_be_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    brain = _fresh_brain()
    assert brain.delete_pod("default") is False
    assert any(p["id"] == "default" for p in brain.list_pods())


def test_specialist_library_crud_and_default_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    brain = _fresh_brain()
    # Seeded with a non-empty default catalog.
    assert len(brain.list_library()) >= 1
    s = brain.add_specialist("QA Tester", "Runs tests", toolsets=["terminal", "file"])
    assert s["toolsets"] == ["terminal", "file"]
    assert s["id"] in {x["id"] for x in brain.list_library()}
    assert brain.delete_specialist(s["id"]) is True
    assert s["id"] not in {x["id"] for x in brain.list_library()}


# ---------------------------------------------------------------------------
# Brain composition contract (the prompt-caching-safe context block)
# ---------------------------------------------------------------------------


def test_compose_context_includes_pod_brain_but_isolates(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    brain = _fresh_brain()
    brain.add_brain_entry("Agency rule", "Always cite sources.")
    pod = brain.add_pod("Acme", "B2B SaaS")
    brain.add_pod_brain_entry(pod["id"], "Mascot", "A blue otter named Pim.")

    # Composing for the pod must surface BOTH the agency brain and the pod's
    # own knowledge, plus the isolation instruction.
    ctx = brain.compose_context(pod["id"])
    assert "Always cite sources." in ctx          # agency brain
    assert "Pim" in ctx                            # pod brain
    assert "isolated" in ctx.lower()               # isolation directive
    assert "SPECIALIST LIBRARY" in ctx             # library composed in

    # Composing for the DEFAULT pod must NOT leak the Acme pod's knowledge.
    ctx_default = brain.compose_context("default")
    assert "Pim" not in ctx_default
    assert "Always cite sources." in ctx_default   # agency brain still present


def test_compose_context_empty_when_nothing_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    brain = _fresh_brain()
    # Wipe the seeded org + library so only emptiness remains.
    brain.set_org([])
    for s in list(brain.list_library()):
        brain.delete_specialist(s["id"])
    assert brain.compose_context() == ""


# ---------------------------------------------------------------------------
# Mission bookkeeping, metrics shape, chaining
# ---------------------------------------------------------------------------


def test_mission_to_public_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    m = engine_mod.Mission(id="abc", prompt="hi")
    pub = m.to_public()
    # Contract: the public dict must always carry these keys for the UI.
    for key in ("id", "prompt", "status", "pod", "chained_from",
                "metrics", "events", "commander_stream"):
        assert key in pub
    for mkey in ("subagents_spawned", "total_tokens", "cost_usd"):
        assert mkey in pub["metrics"]


def test_info_reports_ready_when_creds_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    # Probe resolves creds WITHOUT building the AIAgent (no network).
    monkeypatch.setattr(
        engine_mod, "resolve_hq_credentials",
        lambda provider, model: {"provider": "anthropic", "model": "claude-x"},
    )
    info = engine.info()
    # Contract: info always exposes these keys for the dashboard status dot.
    for key in ("provider", "model", "online", "ready", "error"):
        assert key in info
    # Ready (creds resolve) but not online (agent not built yet).
    assert info["ready"] is True
    assert info["online"] is False
    assert info["error"] is None
    assert info["provider"] == "anthropic"
    assert info["model"] == "claude-x"


def test_info_reports_not_ready_on_resolve_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()

    def _boom(provider, model):
        raise RuntimeError("no provider configured")

    monkeypatch.setattr(engine_mod, "resolve_hq_credentials", _boom)
    info = engine.info()
    assert info["ready"] is False
    assert info["online"] is False
    assert "no provider configured" in (info["error"] or "")


def test_probe_failure_is_retried_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    calls = {"n": 0}

    def _flaky(provider, model):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return {"provider": "anthropic", "model": "claude-x"}

    monkeypatch.setattr(engine_mod, "resolve_hq_credentials", _flaky)
    # First call: failure is reported, not cached as permanent.
    assert engine.info()["ready"] is False
    # Second call: re-probes and now resolves (fixed config reflects live).
    second = engine.info()
    assert second["ready"] is True and second["provider"] == "anthropic"


def test_finalize_turn_raises_on_core_error(tmp_path, monkeypatch):
    # When the core's run_conversation reports an error (billing/auth/HTTP 4xx),
    # the mission must FAIL with that message — not be silently "completed".
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="m1", prompt="p")
    res = {"final_response": None, "error": "HTTP 400: credit balance too low"}
    with pytest.raises(RuntimeError) as ei:
        engine._finalize_turn(m, res)
    assert "credit balance too low" in str(ei.value)


def test_finalize_turn_raises_on_empty_no_delegation(tmp_path, monkeypatch):
    # Empty answer + zero subagents = the turn produced nothing (a swallowed
    # transport/model failure). Treat it as a failure, not success.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="m1", prompt="p")
    with pytest.raises(RuntimeError):
        engine._finalize_turn(m, {"final_response": "", "error": None})


def test_finalize_turn_returns_text_on_success(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="m1", prompt="p")
    out = engine._finalize_turn(m, {"final_response": "PONG", "error": None})
    assert out == "PONG"
    # Plain-string returns (chat() fallback) also pass through.
    assert engine._finalize_turn(m, "hello") == "hello"


def test_finalize_turn_allows_empty_when_subagents_dispatched(tmp_path, monkeypatch):
    # A Commander that fanned all work to subagents and returned no summary
    # text is a legitimate (if terse) completion — must NOT be failed.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="m1", prompt="p")
    m.metrics["subagents_spawned"] = 2
    assert engine._finalize_turn(m, {"final_response": "", "error": None}) == ""


def test_record_usage_computes_positive_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="m1", prompt="p")

    class _FakeAgent:
        session_input_tokens = 0
        session_output_tokens = 0
        session_total_tokens = 0
        session_estimated_cost_usd = 0.0

    agent = _FakeAgent()
    pre = engine_mod._token_snapshot(agent)
    # Simulate the agent's cumulative counters advancing during the turn.
    agent.session_input_tokens = 100
    agent.session_output_tokens = 40
    agent.session_total_tokens = 140
    agent.session_estimated_cost_usd = 0.0021
    engine._record_usage(m, agent, pre)
    assert m.metrics["input_tokens"] == 100
    assert m.metrics["output_tokens"] == 40
    assert m.metrics["total_tokens"] == 140
    assert m.metrics["cost_usd"] == pytest.approx(0.0021, abs=1e-6)


def test_record_usage_never_negative(tmp_path, monkeypatch):
    """If counters reset mid-flight, deltas clamp to 0 (never negative spend)."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="m1", prompt="p")

    class _FakeAgent:
        session_input_tokens = 500
        session_output_tokens = 200
        session_total_tokens = 700
        session_estimated_cost_usd = 0.05

    agent = _FakeAgent()
    pre = engine_mod._token_snapshot(agent)
    agent.session_input_tokens = 0  # reset
    agent.session_total_tokens = 0
    engine._record_usage(m, agent, pre)
    assert m.metrics["input_tokens"] == 0
    assert m.metrics["total_tokens"] == 0
    assert m.metrics["cost_usd"] >= 0.0


def test_mission_chaining_composes_upstream_result(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    # Seed a finished upstream mission directly (no agent run needed).
    upstream = engine_mod.Mission(id="up1", prompt="Find the capital of France.")
    upstream.status = "completed"
    upstream.result = "Paris is the capital of France."
    with engine._missions_lock:
        engine._missions[upstream.id] = upstream

    # Patch out the background thread so start_mission doesn't try to run an
    # agent — we only want to inspect the composed prompt.
    monkeypatch.setattr(engine_mod.threading, "Thread",
                        lambda *a, **k: type("T", (), {"start": lambda self: None})())
    child = engine.start_mission("Write a haiku about it.", chained_from="up1")
    assert child.chained_from == "up1"
    assert "Paris is the capital of France." in child.prompt
    assert "Write a haiku about it." in child.prompt


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def test_schedule_interval_floor_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine = _fresh_engine()
    s = engine.add_schedule("ping", interval=1, label="too fast")
    # Interval is clamped to the engine's minimum floor.
    assert s.interval >= engine._MIN_INTERVAL


def test_tick_schedules_fires_due_and_reschedules(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    fired_prompts = []
    # Stub start_mission so no agent runs; just record the fire.
    monkeypatch.setattr(engine, "start_mission",
                        lambda prompt, pod="default", **k: fired_prompts.append(prompt))
    s = engine.add_schedule("daily report", interval=3600)
    # Not due yet (next_run is ~now+interval).
    assert engine.tick_schedules(now=time.time()) == []
    # Force due and tick.
    with engine._schedules_lock:
        engine._schedules[s.id].next_run = time.time() - 1
    fired = engine.tick_schedules(now=time.time())
    assert s.id in fired
    assert fired_prompts == ["daily report"]
    # After firing, run_count incremented and next_run pushed into the future.
    sched = {x["id"]: x for x in engine.list_schedules()}[s.id]
    assert sched["run_count"] == 1
    assert sched["next_run"] > time.time()


def test_disabled_schedule_does_not_fire(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine = _fresh_engine()
    fired = []
    monkeypatch.setattr(engine, "start_mission",
                        lambda prompt, pod="default", **k: fired.append(prompt))
    s = engine.add_schedule("x", interval=60)
    engine.set_schedule_enabled(s.id, False)
    with engine._schedules_lock:
        engine._schedules[s.id].next_run = time.time() - 1
    assert engine.tick_schedules(now=time.time()) == []
    assert fired == []
    assert engine.delete_schedule(s.id) is True


# ---------------------------------------------------------------------------
# Inter-pod analytics
# ---------------------------------------------------------------------------


def test_pod_analytics_rolls_up_by_pod(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    pod = engine.brain.add_pod("Acme")
    # Two completed missions in the pod, one failed in default.
    for i in range(2):
        m = engine_mod.Mission(id=f"a{i}", prompt="p", pod=pod["id"])
        m.status = "completed"
        m.started_at = 1000.0
        m.finished_at = 1002.0
        m.metrics["total_tokens"] = 50
        m.metrics["cost_usd"] = 0.01
        with engine._missions_lock:
            engine._missions[m.id] = m
    bad = engine_mod.Mission(id="b0", prompt="p", pod="default")
    bad.status = "failed"
    with engine._missions_lock:
        engine._missions[bad.id] = bad

    rows = {r["id"]: r for r in engine.pod_analytics()}
    assert rows[pod["id"]]["missions"] == 2
    assert rows[pod["id"]]["completed"] == 2
    assert rows[pod["id"]]["success_rate"] == 100.0
    assert rows[pod["id"]]["tokens"] == 100
    assert rows[pod["id"]]["cost_usd"] == pytest.approx(0.02, abs=1e-6)
    assert rows[pod["id"]]["avg_duration"] == 2.0
    assert rows["default"]["missions"] == 1
    assert rows["default"]["completed"] == 0
    assert rows["default"]["success_rate"] == 0.0


def test_stats_aggregate_includes_tokens_and_cost(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine_mod = importlib.import_module("hermes_hq.engine")
    engine = engine_mod.HQEngine()
    m = engine_mod.Mission(id="x", prompt="p")
    m.status = "completed"
    m.metrics["total_tokens"] = 123
    m.metrics["cost_usd"] = 0.5
    with engine._missions_lock:
        engine._missions[m.id] = m
    stats = engine.stats()
    assert stats["tokens_total"] == 123
    assert stats["cost_total"] == pytest.approx(0.5, abs=1e-6)
    assert stats["missions_total"] == 1


# ---------------------------------------------------------------------------
# Server: every feature is wired as a route
# ---------------------------------------------------------------------------


def test_app_registers_all_feature_routes(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    server = importlib.import_module("hermes_hq.server")
    app = server.create_app()
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    # Contract: each shipped capability has its endpoint present.
    required = {
        "/api/mission", "/api/missions", "/api/stats", "/api/export",
        "/api/brain", "/api/org", "/api/pods", "/api/stream",
        "/api/library", "/api/analytics/pods", "/api/schedules",
        "/api/depth", "/api/pause",
    }
    missing = required - paths
    assert not missing, f"missing routes: {missing}"
