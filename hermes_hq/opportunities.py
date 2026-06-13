"""HERMES HQ — Opportunity Assistant (human-in-the-loop income pipeline).

This module implements an APPROVAL-GATED opportunity queue. The design rule,
stated up front so it can never drift:

    NO agent action that spends money, sends anything outbound, signs up for an
    account, or commits the user to anything executes automatically. Ever. The
    agents may only RESEARCH and DRAFT. A human (Robin) must explicitly approve
    each opportunity before any outbound/financial step is taken — and even
    after approval, the actual outbound step is performed by the human or by an
    explicitly human-triggered action, never silently by a background loop.

What this module DOES:
  - Stores "opportunities": research findings + drafts the agents produced
    (e.g. a freelance gig found + a drafted proposal, a content idea + a draft).
  - Tracks each through an explicit state machine:
        draft -> pending_review -> approved -> archived
                              \\-> rejected
  - Flags any opportunity whose execution would touch money or send something
    outbound as `requires_approval=True` and `blocked_until_approved=True`.
  - Persists to JSON atomically (temp file + os.replace), thread-safe via RLock,
    exactly like hermes_hq/brain.py — the proven pattern in this codebase.

What this module DOES NOT do (by design, not by omission):
  - It does NOT send emails, submit forms, place bids, trade, or move money.
  - It does NOT auto-approve anything.
  - It does NOT promise income. It is a research + drafting + review surface.

The queue is consumed by the dashboard and the engine. The engine auto-captures
mission results into the queue as `draft` items; nothing leaves `draft`/
`pending_review` without a human action via the API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("hermes_hq")


# --- states -----------------------------------------------------------------

STATE_DRAFT = "draft"                  # agent produced it; not yet surfaced for review
STATE_PENDING = "pending_review"       # awaiting Robin's decision
STATE_APPROVED = "approved"            # Robin approved; outbound step now permitted (manual)
STATE_REJECTED = "rejected"            # Robin declined
STATE_ARCHIVED = "archived"            # done / filed away

VALID_STATES = {STATE_DRAFT, STATE_PENDING, STATE_APPROVED, STATE_REJECTED, STATE_ARCHIVED}

# Allowed transitions. Anything not listed is refused — the gate cannot be
# bypassed by passing an arbitrary target state.
_TRANSITIONS: Dict[str, set] = {
    STATE_DRAFT: {STATE_PENDING, STATE_REJECTED, STATE_ARCHIVED},
    STATE_PENDING: {STATE_APPROVED, STATE_REJECTED, STATE_ARCHIVED},
    STATE_APPROVED: {STATE_ARCHIVED, STATE_REJECTED},
    STATE_REJECTED: {STATE_ARCHIVED},
    STATE_ARCHIVED: set(),
}


# --- risk classification ------------------------------------------------------

# Phrases that mean "this would touch money or send something outbound." If an
# opportunity's action text matches any of these, it is hard-gated: it cannot be
# executed without explicit human approval, and even then only via a manual step.
_OUTBOUND_MONEY_PATTERNS = [
    r"\bsend(ing)?\b.*\b(email|message|dm|reply|proposal|invoice|quote)\b",
    r"\bemail\b", r"\bsmtp\b", r"\bsubmit\b", r"\bapply\b", r"\bbid\b",
    r"\bpost(ing)?\b.*\b(listing|ad|offer|gig|comment|reply)\b",
    r"\bpurchase\b", r"\bpay(ment|out)?\b", r"\bcheckout\b", r"\bsubscribe\b",
    r"\bwire\b", r"\btransfer\b.*\b(money|funds|usd|eur|crypto)\b",
    r"\btrade\b", r"\bbuy\b", r"\bsell\b", r"\binvest\b", r"\bdeposit\b",
    r"\bwithdraw\b", r"\bsign[ -]?up\b", r"\bregister\b.*\baccount\b",
    r"\bcontract\b", r"\bcredit card\b", r"\bbank\b", r"\bpaypal\b", r"\bstripe\b",
]
_OUTBOUND_RE = re.compile("|".join(_OUTBOUND_MONEY_PATTERNS), re.IGNORECASE)


def classify_risk(action_text: str) -> Dict[str, Any]:
    """Decide whether an action touches money/outbound and must be approval-gated.

    Returns a dict with `requires_approval` and the matched signal (for audit).
    Defaults to requiring approval when uncertain — fail safe, never fail open.
    """
    text = (action_text or "").strip()
    if not text:
        # No described action = nothing to execute; safe to leave as a draft note.
        return {"requires_approval": False, "signal": None, "reason": "no action described"}
    m = _OUTBOUND_RE.search(text)
    if m:
        return {
            "requires_approval": True,
            "signal": m.group(0),
            "reason": "matched outbound/financial pattern",
        }
    # Conservative default: anything that reads like an imperative action we
    # haven't positively cleared still requires a human glance.
    return {"requires_approval": True, "signal": None, "reason": "default-deny (human review)"}


def _opp_dir() -> str:
    try:
        from hermes_constants import get_hermes_home

        base = str(get_hermes_home())
    except Exception:
        base = os.path.expanduser("~/.hermes")
    return os.path.join(base, "hermes_hq")


def _opp_path() -> str:
    return os.path.join(_opp_dir(), "opportunities.json")


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return f"opp_{uuid.uuid4().hex[:10]}"


@dataclass
class Opportunity:
    """A researched income opportunity + the draft an agent produced for it.

    `proposed_action` is the human-readable next step (e.g. "send this proposal
    to the client via Upwork"). `requires_approval` / `blocked_until_approved`
    are derived from it via classify_risk and are the enforcement flags the rest
    of the system honours.
    """

    id: str
    title: str
    category: str = "general"          # freelance | content | research | product | other
    summary: str = ""                  # what the opportunity is
    source: str = ""                   # where it came from (url, platform, mission id)
    draft: str = ""                    # the agent-produced draft (proposal/content/etc.)
    proposed_action: str = ""          # the next step a human would take
    est_value: str = ""                # free-text estimate; NEVER a promise
    state: str = STATE_DRAFT
    requires_approval: bool = True
    blocked_until_approved: bool = True
    risk_signal: Optional[str] = None  # what triggered the gate (audit trail)
    mission_id: Optional[str] = None   # the mission that produced it, if any
    pod: str = "default"
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    history: List[Dict[str, Any]] = field(default_factory=list)  # state-change audit log

    def to_public(self) -> Dict[str, Any]:
        return asdict(self)


class OpportunityQueue:
    """Thread-safe, atomically-persisted, approval-gated opportunity store.

    Mirrors hermes_hq/brain.py: a single RLock guards all access; writes go to a
    temp file then os.replace. No method here can move an item to `approved`
    without an explicit human-triggered approve() call.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[str, Opportunity] = {}
        self._dir = _opp_dir()
        self._path = _opp_path()
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if not os.path.isfile(self._path):
                self._save()
                return
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for rec in data.get("opportunities", []):
                try:
                    # Only carry known fields so older/newer files merge safely.
                    opp = Opportunity(
                        id=rec.get("id") or _new_id(),
                        title=rec.get("title", "Untitled"),
                        category=rec.get("category", "general"),
                        summary=rec.get("summary", ""),
                        source=rec.get("source", ""),
                        draft=rec.get("draft", ""),
                        proposed_action=rec.get("proposed_action", ""),
                        est_value=rec.get("est_value", ""),
                        state=rec.get("state", STATE_DRAFT) if rec.get("state") in VALID_STATES else STATE_DRAFT,
                        requires_approval=bool(rec.get("requires_approval", True)),
                        blocked_until_approved=bool(rec.get("blocked_until_approved", True)),
                        risk_signal=rec.get("risk_signal"),
                        mission_id=rec.get("mission_id"),
                        pod=rec.get("pod", "default"),
                        created_at=rec.get("created_at", _now()),
                        updated_at=rec.get("updated_at", _now()),
                        history=rec.get("history", []) or [],
                    )
                    self._items[opp.id] = opp
                except Exception as exc:  # pragma: no cover
                    logger.debug("skip bad opportunity record: %s", exc)
            logger.info("opportunities loaded: %d", len(self._items))
        except Exception as exc:  # pragma: no cover
            logger.debug("opportunities load failed: %s", exc)

    def _save(self) -> None:
        try:
            os.makedirs(self._dir, exist_ok=True)
            tmp = self._path + ".tmp"
            with self._lock:
                payload = {
                    "version": 1,
                    "updated_at": _now(),
                    "opportunities": [o.to_public() for o in self._items.values()],
                }
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, default=str, indent=2)
                os.replace(tmp, self._path)
        except Exception as exc:  # pragma: no cover
            logger.debug("opportunities save failed: %s", exc)

    # -- audit --------------------------------------------------------------

    @staticmethod
    def _audit(opp: Opportunity, action: str, note: str = "") -> None:
        opp.history.append({"t": _now(), "action": action, "note": note})
        # keep the audit log bounded
        if len(opp.history) > 100:
            opp.history = opp.history[-100:]
        opp.updated_at = _now()

    # -- create -------------------------------------------------------------

    def add(
        self,
        title: str,
        *,
        category: str = "general",
        summary: str = "",
        source: str = "",
        draft: str = "",
        proposed_action: str = "",
        est_value: str = "",
        mission_id: Optional[str] = None,
        pod: str = "default",
    ) -> Opportunity:
        """Create a new opportunity in `draft`. Risk-classified at creation.

        The opportunity is ALWAYS created in `draft` — never `approved`. Risk
        flags are computed from proposed_action and stored for the gate.
        """
        risk = classify_risk(proposed_action)
        opp = Opportunity(
            id=_new_id(),
            title=(title or "Untitled").strip(),
            category=(category or "general").strip(),
            summary=(summary or "").strip(),
            source=(source or "").strip(),
            draft=(draft or "").strip(),
            proposed_action=(proposed_action or "").strip(),
            est_value=(est_value or "").strip(),
            state=STATE_DRAFT,
            requires_approval=bool(risk["requires_approval"]),
            blocked_until_approved=bool(risk["requires_approval"]),
            risk_signal=risk.get("signal"),
            mission_id=mission_id,
            pod=(pod or "default"),
        )
        self._audit(opp, "created", risk.get("reason", ""))
        with self._lock:
            self._items[opp.id] = opp
        self._save()
        return opp

    # -- read ---------------------------------------------------------------

    def list(self, *, state: Optional[str] = None, pod: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            out = []
            for o in self._items.values():
                if state and o.state != state:
                    continue
                if pod and o.pod != pod:
                    continue
                out.append(o.to_public())
        out.sort(key=lambda r: r.get("updated_at", 0), reverse=True)
        return out

    def get(self, opp_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            o = self._items.get(opp_id)
            return o.to_public() if o else None

    # -- state machine ------------------------------------------------------

    def _transition(self, opp_id: str, target: str, *, actor: str, note: str = "") -> Optional[Dict[str, Any]]:
        if target not in VALID_STATES:
            raise ValueError(f"unknown state: {target}")
        with self._lock:
            o = self._items.get(opp_id)
            if not o:
                return None
            allowed = _TRANSITIONS.get(o.state, set())
            if target not in allowed:
                raise ValueError(
                    f"illegal transition {o.state} -> {target} "
                    f"(allowed: {sorted(allowed) or 'none'})"
                )
            o.state = target
            self._audit(o, f"-> {target}", f"by {actor}: {note}" if note else f"by {actor}")
            result = o.to_public()
        self._save()
        return result

    def submit_for_review(self, opp_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
        """Move a draft into the human review queue."""
        return self._transition(opp_id, STATE_PENDING, actor="agent", note=note)

    def approve(self, opp_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
        """HUMAN-ONLY approval. The only path that clears the gate.

        After approval, blocked_until_approved is set False so the dashboard may
        offer the manual outbound step — but this method itself performs NO
        outbound action. It only records that Robin authorised the next step.
        """
        result = self._transition(opp_id, STATE_APPROVED, actor="human", note=note)
        if result is not None:
            with self._lock:
                o = self._items.get(opp_id)
                if o:
                    o.blocked_until_approved = False
                    self._audit(o, "approval_cleared_gate", note)
            self._save()
            return self.get(opp_id)
        return result

    def reject(self, opp_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
        """HUMAN-ONLY rejection."""
        return self._transition(opp_id, STATE_REJECTED, actor="human", note=note)

    def archive(self, opp_id: str, *, note: str = "") -> Optional[Dict[str, Any]]:
        return self._transition(opp_id, STATE_ARCHIVED, actor="human", note=note)

    def delete(self, opp_id: str) -> bool:
        with self._lock:
            existed = opp_id in self._items
            self._items.pop(opp_id, None)
        if existed:
            self._save()
        return existed

    # -- gate check ---------------------------------------------------------

    def can_execute_outbound(self, opp_id: str) -> Dict[str, Any]:
        """The single source of truth the rest of the system must consult before
        ANY outbound/financial step. Returns {allowed: bool, reason: str}.

        allowed is True ONLY when a human has approved AND the gate is cleared.
        """
        with self._lock:
            o = self._items.get(opp_id)
        if not o:
            return {"allowed": False, "reason": "no such opportunity"}
        if o.state != STATE_APPROVED:
            return {"allowed": False, "reason": f"not approved (state={o.state})"}
        if o.blocked_until_approved:
            return {"allowed": False, "reason": "gate not cleared"}
        return {"allowed": True, "reason": "human-approved"}

    # -- stats --------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counts: Dict[str, int] = {s: 0 for s in VALID_STATES}
            for o in self._items.values():
                counts[o.state] = counts.get(o.state, 0) + 1
            total = len(self._items)
        return {
            "total": total,
            "by_state": counts,
            "pending_review": counts.get(STATE_PENDING, 0),
        }
