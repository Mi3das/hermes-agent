"""HERMES HQ brain -- the agency knowledge store, org chart, and client pods.

This module implements the three "agent company" pillars from the HERMES HQ
design, all persisted to a single JSON file so they survive app restarts:

1. **gBRAIN (agency brain)** -- the company's shared knowledge: playbooks,
   voice/tone, conventions, frameworks. Each entry is a titled note. The brain
   text is composed into the HQ Commander's system prompt so every mission
   reads from it.

2. **Org chart** -- the configurable taxonomy of Department Verticals, each
   owning Specialist agents, each owning Scoped Sub-agents. The Commander is
   told which verticals/specialists exist so it routes work to them and the
   dashboard renders the hierarchy.

3. **Client Pods** -- isolated workspaces. Each pod has its own brain entries
   and (optionally) its own provider/model. Missions are tagged with a pod id;
   the pod's brain composes *on top of* the agency brain for that mission, and
   missions are filtered per pod so there is no context bleeding across pods.

The store is thread-safe (a single lock guards all reads/writes) and writes are
atomic (temp file + os.replace).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes_hq")


def _brain_dir() -> str:
    """Directory for the gBRAIN store, honouring HERMES_HOME / profiles.

    Resolved lazily so tests (HERMES_HOME tempdir) and non-default profiles
    write to the right place instead of the real ``~/.hermes``.
    """
    try:
        from hermes_constants import get_hermes_home

        base = str(get_hermes_home())
    except Exception:
        base = os.path.expanduser("~/.hermes")
    return os.path.join(base, "hermes_hq")


def _brain_path() -> str:
    return os.path.join(_brain_dir(), "gbrain.json")


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# Default org chart, mirroring the "agent company" reference. Users can edit it
# live via the dashboard; this is just the starting taxonomy.
_DEFAULT_ORG: List[Dict[str, Any]] = [
    {
        "id": "vert_content",
        "name": "Content",
        "outcome": "On-brand written assets",
        "specialists": [
            {"name": "Blog Writer", "subagents": ["Outline Generator", "Source Finder", "Fact Checker"]},
            {"name": "Content Researcher", "subagents": ["Quote Extractor", "Brief Builder"]},
            {"name": "Repurposing Agent", "subagents": ["Thread Splitter", "Snippet Cutter"]},
        ],
    },
    {
        "id": "vert_email",
        "name": "Lifecycle Email",
        "outcome": "Automated nurture & retention",
        "specialists": [
            {"name": "Campaign Strategist", "subagents": ["Flow Trigger Builder", "Audience Segmenter"]},
            {"name": "Email Copywriter", "subagents": ["Subject Line Variants", "Spam Checker"]},
            {"name": "Flow Builder", "subagents": ["A/B Test Creator", "UTM Builder"]},
        ],
    },
    {
        "id": "vert_seo",
        "name": "Technical SEO",
        "outcome": "Crawlable, ranked pages",
        "specialists": [
            {"name": "Technical SEO Analyst", "subagents": ["Log Analyzer", "Indexability Tester"]},
            {"name": "On-Page Specialist", "subagents": ["Canonical Checker", "Sitemap Validator"]},
            {"name": "Schema Specialist", "subagents": ["Markup Generator", "Rich Result Tester"]},
        ],
    },
    {
        "id": "vert_ads",
        "name": "Paid Ads",
        "outcome": "Efficient paid acquisition",
        "specialists": [
            {"name": "Ads Strategist", "subagents": ["Ad Copy Variants", "Hook Generator"]},
            {"name": "Audience Research", "subagents": ["Landing Page Critic", "Audience Segmenter"]},
            {"name": "Budget Optimizer", "subagents": ["ROAS Forecaster", "Bid Adjuster"]},
        ],
    },
]


# Default specialist library: a reusable catalog of specialist roles the org
# chart can pull from. Each entry pairs a role with the toolsets a subagent
# acting as that specialist should typically get, so the Commander can map a
# named specialist to a concrete delegate_task toolset list. Editable live.
_DEFAULT_LIBRARY: List[Dict[str, Any]] = [
    {"id": "spec_researcher", "name": "Researcher",
     "description": "Gathers and synthesises information from the web.",
     "toolsets": ["web"]},
    {"id": "spec_writer", "name": "Writer",
     "description": "Produces on-brand written assets from a brief.",
     "toolsets": ["web"]},
    {"id": "spec_engineer", "name": "Engineer",
     "description": "Reads/writes code and runs commands in a sandbox.",
     "toolsets": ["terminal", "file"]},
    {"id": "spec_analyst", "name": "Data Analyst",
     "description": "Processes data and computes metrics.",
     "toolsets": ["terminal", "file"]},
    {"id": "spec_web", "name": "Web Operator",
     "description": "Interacts with live web pages (forms, clicks, scraping).",
     "toolsets": ["browser"]},
]


def _default_store() -> Dict[str, Any]:
    return {
        "version": 1,
        # Agency-level knowledge entries.
        "brain": [],
        # Department verticals taxonomy.
        "org": list(_DEFAULT_ORG),
        # Reusable specialist role catalog the org chart draws from.
        "library": list(_DEFAULT_LIBRARY),
        # Client pods (isolated workspaces). The "default" pod is the agency
        # itself -- missions with no explicit pod belong here.
        "pods": [
            {
                "id": "default",
                "name": "Agency (Default)",
                "description": "Shared agency workspace. Missions with no pod live here.",
                "brain": [],
                "provider": None,
                "model": None,
                "created_at": _now(),
            }
        ],
    }


class HQBrain:
    """Thread-safe, JSON-persisted store for brain entries, org chart, pods."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: Dict[str, Any] = _default_store()
        # Resolve persistence paths once at construction so a single store
        # instance is stable even if HERMES_HOME changes later in-process.
        self._dir = _brain_dir()
        self._path = _brain_path()
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if not os.path.isfile(self._path):
                self._save()  # materialise defaults on first run
                return
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return
            base = _default_store()
            # Merge so missing keys (older files) pick up defaults.
            for key in ("brain", "org", "library", "pods"):
                if isinstance(data.get(key), list) and data[key]:
                    base[key] = data[key]
            base["version"] = data.get("version", 1)
            # Guarantee a default pod always exists.
            if not any(p.get("id") == "default" for p in base["pods"]):
                base["pods"].insert(0, _default_store()["pods"][0])
            self._store = base
            logger.info(
                "gBRAIN loaded: %d entries, %d verticals, %d pods",
                len(base["brain"]), len(base["org"]), len(base["pods"]),
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("gBRAIN load failed: %s", exc)

    def _save(self) -> None:
        try:
            os.makedirs(self._dir, exist_ok=True)
            tmp = self._path + ".tmp"
            with self._lock:
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self._store, fh, default=str, indent=2)
            os.replace(tmp, self._path)
        except Exception as exc:  # pragma: no cover
            logger.debug("gBRAIN save failed: %s", exc)

    # -- agency brain -------------------------------------------------------

    def list_brain(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(e) for e in self._store["brain"]]

    def add_brain_entry(self, title: str, body: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        entry = {
            "id": _new_id("kb"),
            "title": (title or "Untitled").strip(),
            "body": (body or "").strip(),
            "tags": [t.strip() for t in (tags or []) if t.strip()],
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            self._store["brain"].append(entry)
        self._save()
        return entry

    def update_brain_entry(self, entry_id: str, title: Optional[str] = None,
                           body: Optional[str] = None, tags: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            for e in self._store["brain"]:
                if e.get("id") == entry_id:
                    if title is not None:
                        e["title"] = title.strip()
                    if body is not None:
                        e["body"] = body.strip()
                    if tags is not None:
                        e["tags"] = [t.strip() for t in tags if t.strip()]
                    e["updated_at"] = _now()
                    self._save()
                    return dict(e)
        return None

    def delete_brain_entry(self, entry_id: str) -> bool:
        with self._lock:
            before = len(self._store["brain"])
            self._store["brain"] = [e for e in self._store["brain"] if e.get("id") != entry_id]
            changed = len(self._store["brain"]) != before
        if changed:
            self._save()
        return changed

    # -- org chart ----------------------------------------------------------

    def get_org(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._store["org"]]

    def set_org(self, org: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace the whole org chart. Each vertical needs name; ids are minted."""
        clean: List[Dict[str, Any]] = []
        for v in org or []:
            if not isinstance(v, dict) or not (v.get("name") or "").strip():
                continue
            specialists = []
            for s in v.get("specialists", []) or []:
                if isinstance(s, dict) and (s.get("name") or "").strip():
                    specialists.append({
                        "name": s["name"].strip(),
                        "subagents": [str(x).strip() for x in (s.get("subagents") or []) if str(x).strip()],
                    })
            clean.append({
                "id": v.get("id") or _new_id("vert"),
                "name": v["name"].strip(),
                "outcome": (v.get("outcome") or "").strip(),
                "specialists": specialists,
            })
        with self._lock:
            self._store["org"] = clean
        self._save()
        return clean

    def add_vertical(self, name: str, outcome: str = "") -> Dict[str, Any]:
        vert = {"id": _new_id("vert"), "name": name.strip(), "outcome": outcome.strip(), "specialists": []}
        with self._lock:
            self._store["org"].append(vert)
        self._save()
        return vert

    def delete_vertical(self, vert_id: str) -> bool:
        with self._lock:
            before = len(self._store["org"])
            self._store["org"] = [v for v in self._store["org"] if v.get("id") != vert_id]
            changed = len(self._store["org"]) != before
        if changed:
            self._save()
        return changed

    # -- specialist library -------------------------------------------------

    def list_library(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(s) for s in self._store.get("library", [])]

    def add_specialist(self, name: str, description: str = "",
                       toolsets: Optional[List[str]] = None) -> Dict[str, Any]:
        spec = {
            "id": _new_id("spec"),
            "name": (name or "Specialist").strip(),
            "description": (description or "").strip(),
            "toolsets": [str(t).strip() for t in (toolsets or []) if str(t).strip()],
        }
        with self._lock:
            self._store.setdefault("library", []).append(spec)
        self._save()
        return spec

    def delete_specialist(self, spec_id: str) -> bool:
        with self._lock:
            lib = self._store.setdefault("library", [])
            before = len(lib)
            self._store["library"] = [s for s in lib if s.get("id") != spec_id]
            changed = len(self._store["library"]) != before
        if changed:
            self._save()
        return changed

    # -- client pods --------------------------------------------------------

    def list_pods(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._pod_public(p) for p in self._store["pods"]]

    @staticmethod
    def _pod_public(p: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": p.get("id"),
            "name": p.get("name"),
            "description": p.get("description", ""),
            "brain": [dict(e) for e in p.get("brain", [])],
            "provider": p.get("provider"),
            "model": p.get("model"),
            "created_at": p.get("created_at"),
        }

    def get_pod(self, pod_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for p in self._store["pods"]:
                if p.get("id") == pod_id:
                    return self._pod_public(p)
        return None

    def add_pod(self, name: str, description: str = "",
                provider: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
        pod = {
            "id": _new_id("pod"),
            "name": (name or "New Client").strip(),
            "description": (description or "").strip(),
            "brain": [],
            "provider": (provider or None),
            "model": (model or None),
            "created_at": _now(),
        }
        with self._lock:
            self._store["pods"].append(pod)
        self._save()
        return self._pod_public(pod)

    def delete_pod(self, pod_id: str) -> bool:
        if pod_id == "default":
            return False  # never delete the agency pod
        with self._lock:
            before = len(self._store["pods"])
            self._store["pods"] = [p for p in self._store["pods"] if p.get("id") != pod_id]
            changed = len(self._store["pods"]) != before
        if changed:
            self._save()
        return changed

    def add_pod_brain_entry(self, pod_id: str, title: str, body: str) -> Optional[Dict[str, Any]]:
        entry = {
            "id": _new_id("kb"),
            "title": (title or "Untitled").strip(),
            "body": (body or "").strip(),
            "created_at": _now(),
            "updated_at": _now(),
        }
        with self._lock:
            for p in self._store["pods"]:
                if p.get("id") == pod_id:
                    p.setdefault("brain", []).append(entry)
                    self._save()
                    return entry
        return None

    def delete_pod_brain_entry(self, pod_id: str, entry_id: str) -> bool:
        with self._lock:
            for p in self._store["pods"]:
                if p.get("id") == pod_id:
                    before = len(p.get("brain", []))
                    p["brain"] = [e for e in p.get("brain", []) if e.get("id") != entry_id]
                    changed = len(p["brain"]) != before
                    if changed:
                        self._save()
                    return changed
        return False

    # -- prompt composition -------------------------------------------------

    def compose_context(self, pod_id: Optional[str] = None) -> str:
        """Build the brain context block injected into the Commander prompt.

        Composes (in order): the org chart summary, the agency brain entries,
        and -- when a pod is given -- that pod's identity + its own brain on top.
        Returns an empty string when there is nothing to add.
        """
        with self._lock:
            org = [dict(v) for v in self._store["org"]]
            agency = [dict(e) for e in self._store["brain"]]
            library = [dict(s) for s in self._store.get("library", [])]
            pod = None
            if pod_id and pod_id != "default":
                for p in self._store["pods"]:
                    if p.get("id") == pod_id:
                        pod = self._pod_public(p)
                        break

        parts: List[str] = []

        if org:
            lines = ["## DEPARTMENT VERTICALS (route work to these)"]
            for v in org:
                spec = ", ".join(s.get("name", "") for s in v.get("specialists", []))
                outcome = f" — {v['outcome']}" if v.get("outcome") else ""
                lines.append(f"- {v.get('name','')}{outcome}" + (f"  [specialists: {spec}]" if spec else ""))
            parts.append("\n".join(lines))

        if library:
            lines = ["## SPECIALIST LIBRARY (pick the right role + toolsets per sub-task)"]
            for s in library:
                ts = ", ".join(s.get("toolsets", []))
                desc = f" — {s['description']}" if s.get("description") else ""
                lines.append(
                    f"- {s.get('name','')}{desc}" + (f"  [toolsets: {ts}]" if ts else "")
                )
            parts.append("\n".join(lines))

        if agency:
            lines = ["## AGENCY BRAIN (shared knowledge — apply to all work)"]
            for e in agency:
                lines.append(f"### {e.get('title','')}")
                if e.get("body"):
                    lines.append(e["body"])
            parts.append("\n".join(lines))

        if pod:
            lines = [f"## CLIENT POD: {pod.get('name','')}"]
            if pod.get("description"):
                lines.append(pod["description"])
            if pod.get("brain"):
                lines.append("### Client-specific knowledge (overrides/extends agency brain)")
                for e in pod["brain"]:
                    lines.append(f"- {e.get('title','')}: {e.get('body','')}")
            lines.append(
                "This mission runs INSIDE this client pod. Keep its context "
                "isolated — do not leak details from other clients."
            )
            parts.append("\n".join(lines))

        return "\n\n".join(parts).strip()

    def snapshot(self) -> Dict[str, Any]:
        """Full snapshot for the SSE stream / API."""
        with self._lock:
            return {
                "brain": [dict(e) for e in self._store["brain"]],
                "org": [dict(v) for v in self._store["org"]],
                "library": [dict(s) for s in self._store.get("library", [])],
                "pods": [self._pod_public(p) for p in self._store["pods"]],
            }
