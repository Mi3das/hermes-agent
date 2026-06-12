"""HERMES HQ web server -- FastAPI app for the visual command center.

Endpoints:
  GET  /                     -> dashboard SPA
  GET  /api/info             -> HQ Commander provider/model + config knobs
  POST /api/mission          -> start a mission (returns mission id)
  GET  /api/missions         -> list missions
  GET  /api/mission/{id}     -> one mission's state
  POST /api/pause            -> pause/resume new subagent spawns
  POST /api/interrupt/{sid}  -> interrupt one running subagent
  GET  /api/stream           -> Server-Sent Events: live agent graph + missions

The live agent graph is built from the core's own ``list_active_subagents()``
registry plus HQ's mission bookkeeping -- no separate tracking to drift.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hermes_hq.engine import HQEngine

_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC = os.path.join(_HERE, "static")


def _delegation_config() -> Dict[str, Any]:
    """Surface the delegation knobs that shape the ecosystem, for the UI."""
    try:
        from tools.delegate_tool import (
            _get_max_concurrent_children,
            _get_max_spawn_depth,
            is_spawn_paused,
        )

        return {
            "max_concurrent_children": _get_max_concurrent_children(),
            "max_spawn_depth": _get_max_spawn_depth(),
            "paused": is_spawn_paused(),
        }
    except Exception:
        return {"max_concurrent_children": None, "max_spawn_depth": None, "paused": False}


def _live_subagents() -> List[Dict[str, Any]]:
    try:
        from tools.delegate_tool import list_active_subagents

        return list_active_subagents()
    except Exception:
        return []


def _set_max_spawn_depth(depth: int) -> int:
    """Persist delegation.max_spawn_depth and update the live runtime config.

    Writes to config.yaml (durable) AND patches the in-memory CLI_CONFIG when
    present so new spawns pick up the value immediately -- delegate_tool's
    ``_load_config()`` checks CLI_CONFIG before disk.
    """
    depth = max(1, int(depth))
    # 1) durable write
    try:
        from hermes_cli.config import load_config, save_config

        cfg = load_config()
        deleg = cfg.get("delegation")
        if not isinstance(deleg, dict):
            deleg = {}
        deleg["max_spawn_depth"] = depth
        cfg["delegation"] = deleg
        save_config(cfg)
    except Exception:
        pass
    # 2) live runtime override (so it takes effect without a disk reload race)
    try:
        from cli import CLI_CONFIG

        deleg = CLI_CONFIG.get("delegation")
        if not isinstance(deleg, dict):
            deleg = {}
        deleg["max_spawn_depth"] = depth
        CLI_CONFIG["delegation"] = deleg
    except Exception:
        pass
    # 3) read back the effective value via the same path delegate_tool uses
    try:
        from tools.delegate_tool import _get_max_spawn_depth

        return _get_max_spawn_depth()
    except Exception:
        return depth


class MissionRequest(BaseModel):
    prompt: str
    pod: Optional[str] = "default"
    chained_from: Optional[str] = None


class ScheduleRequest(BaseModel):
    prompt: str
    interval: float
    pod: Optional[str] = "default"
    label: Optional[str] = ""


class ScheduleToggleRequest(BaseModel):
    enabled: bool


class SpecialistRequest(BaseModel):
    name: str
    description: str = ""
    toolsets: Optional[List[str]] = None


class PauseRequest(BaseModel):
    paused: bool


class DepthRequest(BaseModel):
    depth: int


class BrainEntryRequest(BaseModel):
    title: str
    body: str = ""
    tags: Optional[List[str]] = None


class BrainUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[List[str]] = None


class OrgRequest(BaseModel):
    org: List[Dict[str, Any]]


class VerticalRequest(BaseModel):
    name: str
    outcome: str = ""


class PodRequest(BaseModel):
    name: str
    description: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None


class PodBrainRequest(BaseModel):
    title: str
    body: str = ""


def create_app(provider: Optional[str] = None, model: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="HERMES HQ", version="0.1.0")
    engine = HQEngine(provider=provider, model=model)
    app.state.engine = engine

    # -- static / index -----------------------------------------------------
    if os.path.isdir(_STATIC):
        app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/")
    def index():
        idx = os.path.join(_STATIC, "index.html")
        if os.path.isfile(idx):
            return FileResponse(idx)
        raise HTTPException(404, "dashboard not built")

    # -- info ---------------------------------------------------------------
    @app.get("/api/info")
    def info():
        return {
            "hq": engine.info(),
            "delegation": _delegation_config(),
            "version": "0.1.0",
        }

    # -- missions -----------------------------------------------------------
    @app.post("/api/mission")
    def start_mission(req: MissionRequest):
        prompt = (req.prompt or "").strip()
        if not prompt:
            raise HTTPException(400, "prompt is required")
        # Surface credential errors eagerly so the UI shows a clear message.
        try:
            engine.ensure_agent()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, str(exc))
        mission = engine.start_mission(
            prompt, pod=(req.pod or "default"), chained_from=req.chained_from
        )
        return {"id": mission.id, "status": mission.status, "pod": mission.pod,
                "chained_from": mission.chained_from}

    @app.get("/api/missions")
    def list_missions(pod: Optional[str] = None):
        return {"missions": engine.list_missions(pod=pod)}

    @app.get("/api/mission/{mission_id}")
    def get_mission(mission_id: str):
        m = engine.get_mission(mission_id)
        if not m:
            raise HTTPException(404, "no such mission")
        return m

    @app.post("/api/mission/{mission_id}/cancel")
    def cancel_mission(mission_id: str):
        ok = engine.cancel_mission(mission_id)
        if not ok:
            raise HTTPException(409, "mission not running or not found")
        return {"cancelled": True, "id": mission_id}

    @app.post("/api/mission/{mission_id}/rerun")
    def rerun_mission(mission_id: str):
        try:
            engine.ensure_agent()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, str(exc))
        m = engine.rerun_mission(mission_id)
        if not m:
            raise HTTPException(404, "no such mission")
        return {"id": m.id, "status": m.status}

    @app.delete("/api/mission/{mission_id}")
    def delete_mission(mission_id: str):
        ok = engine.delete_mission(mission_id)
        if not ok:
            raise HTTPException(404, "no such mission")
        return {"deleted": True, "id": mission_id}

    # -- ecosystem stats + history ------------------------------------------
    @app.get("/api/stats")
    def stats():
        return engine.stats()

    @app.post("/api/history/clear")
    def clear_history():
        removed = engine.clear_history()
        return {"removed": removed}

    @app.get("/api/export")
    def export_all():
        """Full machine-readable export of every mission for archival."""
        return {
            "exported_at": time.time(),
            "hq": engine.info(),
            "stats": engine.stats(),
            "missions": engine.list_missions(),
        }

    @app.post("/api/shutdown")
    def shutdown():
        """Graceful stop: flush state, then signal the process to exit.

        Used by the desktop launcher's AppleScript ``quit`` path. The launcher
        owns the process group and reaps everything; we just need to make the
        server process exit cleanly after saving. We send SIGTERM to ourselves
        on a short delay so this HTTP response is delivered first.
        """
        try:
            engine.shutdown()
        except Exception:
            pass

        def _die():
            # Give the HTTP response time to flush, then hard-exit. We use
            # os._exit (not SIGTERM) because uvicorn's graceful shutdown blocks
            # on the long-lived /api/stream SSE generator, which never returns.
            time.sleep(0.4)
            os._exit(0)

        threading.Thread(target=_die, daemon=True).start()
        return {"stopping": True}

    # -- gBRAIN (agency knowledge) ------------------------------------------
    @app.get("/api/brain")
    def get_brain():
        return {"brain": engine.brain.list_brain()}

    @app.post("/api/brain")
    def add_brain(req: BrainEntryRequest):
        title = (req.title or "").strip()
        if not title:
            raise HTTPException(400, "title is required")
        return engine.brain.add_brain_entry(title, req.body or "", req.tags)

    @app.put("/api/brain/{entry_id}")
    def update_brain(entry_id: str, req: BrainUpdateRequest):
        e = engine.brain.update_brain_entry(entry_id, req.title, req.body, req.tags)
        if not e:
            raise HTTPException(404, "no such brain entry")
        return e

    @app.delete("/api/brain/{entry_id}")
    def delete_brain(entry_id: str):
        ok = engine.brain.delete_brain_entry(entry_id)
        if not ok:
            raise HTTPException(404, "no such brain entry")
        return {"deleted": True, "id": entry_id}

    # -- org chart (verticals -> specialists -> sub-agents) -----------------
    @app.get("/api/org")
    def get_org():
        return {"org": engine.brain.get_org()}

    @app.post("/api/org")
    def set_org(req: OrgRequest):
        return {"org": engine.brain.set_org(req.org)}

    @app.post("/api/org/vertical")
    def add_vertical(req: VerticalRequest):
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        return engine.brain.add_vertical(name, req.outcome or "")

    @app.delete("/api/org/vertical/{vert_id}")
    def delete_vertical(vert_id: str):
        ok = engine.brain.delete_vertical(vert_id)
        if not ok:
            raise HTTPException(404, "no such vertical")
        return {"deleted": True, "id": vert_id}

    # -- client pods (isolated workspaces) ----------------------------------
    @app.get("/api/pods")
    def get_pods():
        return {"pods": engine.brain.list_pods()}

    @app.post("/api/pods")
    def add_pod(req: PodRequest):
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        return engine.brain.add_pod(name, req.description or "", req.provider, req.model)

    @app.delete("/api/pods/{pod_id}")
    def delete_pod(pod_id: str):
        if pod_id == "default":
            raise HTTPException(400, "the default agency pod cannot be deleted")
        ok = engine.brain.delete_pod(pod_id)
        if not ok:
            raise HTTPException(404, "no such pod")
        return {"deleted": True, "id": pod_id}

    @app.post("/api/pods/{pod_id}/brain")
    def add_pod_brain(pod_id: str, req: PodBrainRequest):
        title = (req.title or "").strip()
        if not title:
            raise HTTPException(400, "title is required")
        e = engine.brain.add_pod_brain_entry(pod_id, title, req.body or "")
        if not e:
            raise HTTPException(404, "no such pod")
        return e

    @app.delete("/api/pods/{pod_id}/brain/{entry_id}")
    def delete_pod_brain(pod_id: str, entry_id: str):
        ok = engine.brain.delete_pod_brain_entry(pod_id, entry_id)
        if not ok:
            raise HTTPException(404, "no such pod or entry")
        return {"deleted": True, "id": entry_id}

    # -- specialist library -------------------------------------------------
    @app.get("/api/library")
    def get_library():
        return {"library": engine.brain.list_library()}

    @app.post("/api/library")
    def add_specialist(req: SpecialistRequest):
        name = (req.name or "").strip()
        if not name:
            raise HTTPException(400, "name is required")
        return engine.brain.add_specialist(name, req.description or "", req.toolsets)

    @app.delete("/api/library/{spec_id}")
    def delete_specialist(spec_id: str):
        ok = engine.brain.delete_specialist(spec_id)
        if not ok:
            raise HTTPException(404, "no such specialist")
        return {"deleted": True, "id": spec_id}

    # -- inter-pod analytics ------------------------------------------------
    @app.get("/api/analytics/pods")
    def pod_analytics():
        return {"pods": engine.pod_analytics()}

    # -- recurring mission schedules ----------------------------------------
    @app.get("/api/schedules")
    def list_schedules():
        return {"schedules": engine.list_schedules()}

    @app.post("/api/schedules")
    def add_schedule(req: ScheduleRequest):
        prompt = (req.prompt or "").strip()
        if not prompt:
            raise HTTPException(400, "prompt is required")
        if not req.interval or req.interval <= 0:
            raise HTTPException(400, "interval must be positive (seconds)")
        s = engine.add_schedule(prompt, req.interval, pod=(req.pod or "default"),
                                label=(req.label or ""))
        return s.to_public()

    @app.post("/api/schedules/{schedule_id}/toggle")
    def toggle_schedule(schedule_id: str, req: ScheduleToggleRequest):
        ok = engine.set_schedule_enabled(schedule_id, req.enabled)
        if not ok:
            raise HTTPException(404, "no such schedule")
        return {"id": schedule_id, "enabled": req.enabled}

    @app.delete("/api/schedules/{schedule_id}")
    def delete_schedule(schedule_id: str):
        ok = engine.delete_schedule(schedule_id)
        if not ok:
            raise HTTPException(404, "no such schedule")
        return {"deleted": True, "id": schedule_id}

    # -- live controls ------------------------------------------------------
    @app.post("/api/pause")
    def pause(req: PauseRequest):
        try:
            from tools.delegate_tool import set_spawn_paused

            return {"paused": set_spawn_paused(req.paused)}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, str(exc))

    @app.post("/api/depth")
    def set_depth(req: DepthRequest):
        """Set delegation.max_spawn_depth (1 = flat, 2+ = nested swarms)."""
        effective = _set_max_spawn_depth(req.depth)
        return {"max_spawn_depth": effective}

    @app.get("/api/output/{subagent_id}")
    def subagent_output(subagent_id: str):
        """Live tool-activity stream captured for one subagent."""
        return {"subagent_id": subagent_id, "lines": engine.monitor.lines_for(subagent_id)}

    @app.post("/api/interrupt/{subagent_id}")
    def interrupt(subagent_id: str):
        try:
            from tools.delegate_tool import interrupt_subagent

            ok = interrupt_subagent(subagent_id)
            return {"interrupted": ok}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(500, str(exc))

    # -- live stream (SSE) --------------------------------------------------
    @app.get("/api/stream")
    async def stream():
        async def gen():
            while True:
                subs = _live_subagents()
                mon = engine.monitor.snapshot()
                # Merge live tool-output tail into each active subagent record,
                # and fold in identity (parent_id/depth) the monitor captured.
                for s in subs:
                    sid = s.get("subagent_id")
                    m = mon.get(sid) if sid else None
                    if m:
                        s["output"] = m.get("lines", [])
                        if s.get("parent_id") is None and m.get("parent_id"):
                            s["parent_id"] = m.get("parent_id")
                        if s.get("depth") is None and m.get("depth") is not None:
                            s["depth"] = m.get("depth")
                    else:
                        s["output"] = []
                payload = {
                    "t": time.time(),
                    "subagents": subs,
                    "monitor": mon,
                    "missions": engine.list_missions(),
                    "delegation": _delegation_config(),
                    "stats": engine.stats(),
                    "brain": engine.brain.snapshot(),
                    "schedules": engine.list_schedules(),
                }
                yield f"data: {json.dumps(payload, default=str)}\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
