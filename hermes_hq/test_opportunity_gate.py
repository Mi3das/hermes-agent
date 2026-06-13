"""Real test of the approval gate. No mocks of the queue itself — exercises the
actual OpportunityQueue against a temp HERMES_HOME, per AGENTS.md E2E rule.

Run: python hermes_hq/test_opportunity_gate.py
Exits non-zero on any gate violation.
"""
import os
import sys
import tempfile

# Point HERMES_HOME at a throwaway dir BEFORE importing the queue so it
# persists to the temp location, not the real ~/.hermes.
_tmp = tempfile.mkdtemp(prefix="hq_opp_test_")
os.environ["HERMES_HOME"] = _tmp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_hq.opportunities import (  # noqa: E402
    OpportunityQueue, classify_risk,
    STATE_DRAFT, STATE_PENDING, STATE_APPROVED, STATE_REJECTED,
)

failures = []


def check(cond, msg):
    if cond:
        print(f"  PASS: {msg}")
    else:
        print(f"  FAIL: {msg}")
        failures.append(msg)


print("1. Risk classification")
# Outbound / money actions must be flagged.
for action in [
    "send the proposal to the client via email",
    "submit a bid on the Upwork gig",
    "buy the domain and pay with the credit card",
    "transfer funds to the freelancer",
    "post the listing on the marketplace",
]:
    r = classify_risk(action)
    check(r["requires_approval"], f"flagged outbound/money: {action!r}")

# Empty action = nothing to execute, not gated (but item still a draft).
check(not classify_risk("")["requires_approval"], "empty action not gated")
# Ambiguous non-empty action defaults to requiring review (fail-safe).
check(classify_risk("review the notes")["requires_approval"], "ambiguous action default-denied")

print("2. Queue: creation always starts as draft, gate engaged")
q = OpportunityQueue()
opp = q.add(
    title="Freelance Python gig",
    summary="Client needs a scraper",
    draft="Hi, I can build your scraper...",
    proposed_action="send this proposal to the client via email",
)
check(opp.state == STATE_DRAFT, "new item is draft")
check(opp.requires_approval, "outbound item requires approval")
check(opp.blocked_until_approved, "outbound item blocked until approved")

print("3. Gate blocks execution before approval")
g = q.can_execute_outbound(opp.id)
check(not g["allowed"], f"execution blocked before approval ({g['reason']})")

print("4. Cannot skip review: draft -> approved directly is illegal")
try:
    q.approve(opp.id)  # opp is in draft, not pending
    check(False, "approve from draft should have raised")
except ValueError:
    check(True, "approve from draft refused (must go through review)")

print("5. Proper flow: submit -> approve clears gate")
q.submit_for_review(opp.id)
cur = q.get(opp.id)
check(cur["state"] == STATE_PENDING, "submitted for review")
approved = q.approve(opp.id, note="Robin OK")
check(approved["state"] == STATE_APPROVED, "approved by human")
check(not approved["blocked_until_approved"], "gate cleared after approval")
g2 = q.can_execute_outbound(opp.id)
check(g2["allowed"], "execution allowed only after human approval")

print("6. Rejection path")
opp2 = q.add(title="Spammy gig", proposed_action="send 500 cold emails")
q.submit_for_review(opp2.id)
rej = q.reject(opp2.id, note="no thanks")
check(rej["state"] == STATE_REJECTED, "rejected by human")
check(not q.can_execute_outbound(opp2.id)["allowed"], "rejected item never executable")

print("7. Persistence: reload from disk preserves state + gate")
q2 = OpportunityQueue()  # fresh instance, same temp HERMES_HOME
reloaded = q2.get(opp.id)
check(reloaded is not None, "item persisted across instances")
check(reloaded["state"] == STATE_APPROVED, "approved state persisted")
check(q2.can_execute_outbound(opp.id)["allowed"], "gate state persisted")

print("8. Audit trail present")
check(len(reloaded["history"]) >= 3, f"audit log recorded ({len(reloaded['history'])} entries)")

print()
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S)")
    sys.exit(1)
print("RESULT: ALL GATE CHECKS PASSED")
