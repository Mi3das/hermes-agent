"""Verify REAL mission outcomes flow into the learning engine.

Drives _record_learning_outcome with constructed-but-realistic Mission objects
(the same dataclass the live loop uses) against a temp HERMES_HOME, and asserts
the learning engine recorded actual values — no random/demo data involved.

Run: python hermes_hq/test_learning_wiring.py   (exit 0 = wired correctly)
"""
import os, sys, tempfile, time

os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hq_learn_test_")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hermes_hq.engine import HQEngine, Mission  # noqa: E402

failures = []
def check(cond, msg):
    print(("  PASS: " if cond else "  FAIL: ") + msg)
    if not cond: failures.append(msg)

eng = HQEngine()

print("1. No profiles before any mission runs (fake seed data must be absent)")
check(len(eng.learning_engine.profiles) == 0, "learning store starts empty")

print("2. A completed mission records a REAL outcome")
m = Mission(id="m-real-1", prompt="do a thing", pod="default")
m.started_at = time.time() - 12.0
m.finished_at = time.time()
m.status = "completed"
m.metrics.update({"cost_usd": 0.0123, "total_tokens": 4200, "input_tokens": 3000,
                  "output_tokens": 1200, "subagents_spawned": 2})
eng._record_learning_outcome(m)

profs = eng.learning_engine.profiles
check(len(profs) == 1, "exactly one profile created")
agent_id = list(profs)[0]
p = profs[agent_id]
check(agent_id.startswith("commander:"), f"keyed by commander model ({agent_id})")
check(p.total_missions == 1, "total_missions == 1")
check(p.successful_missions == 1, "counted as success")
check(10.0 <= p.avg_mission_duration <= 14.0, f"real duration recorded ({p.avg_mission_duration:.1f}s)")

print("3. Real cost/token metrics landed in metrics_history")
costs = [mt.value for mt in p.metrics_history if mt.name == "cost_usd"]
toks = [mt.value for mt in p.metrics_history if mt.name == "total_tokens"]
check(costs and abs(costs[0] - 0.0123) < 1e-9, "real cost_usd recorded")
check(toks and toks[0] == 4200, "real total_tokens recorded")

print("4. A failed mission records failure + reason")
m2 = Mission(id="m-real-2", prompt="break", pod="default")
m2.started_at = time.time() - 3.0
m2.finished_at = time.time()
m2.status = "failed"
m2.error = "provider 402: out of credits"
eng._record_learning_outcome(m2)
p = eng.learning_engine.profiles[agent_id]
check(p.total_missions == 2, "second mission counted")
check(p.failed_missions == 1, "failure counted")
check(any("402" in f.get("reason","") for f in p.observed_failures), "real failure reason recorded")

print("5. Cancelled missions are NOT recorded (not a real signal)")
m3 = Mission(id="m-cancel", prompt="x", pod="default")
m3.status = "cancelled"; m3.finished_at = time.time()
eng._record_learning_outcome(m3)
check(eng.learning_engine.profiles[agent_id].total_missions == 2, "cancelled mission skipped")

print("6. Persists to disk and reloads")
eng2 = HQEngine()
check(agent_id in eng2.learning_engine.profiles, "profile persisted across instances")
check(eng2.learning_engine.profiles[agent_id].total_missions == 2, "counts persisted")

print()
if failures:
    print(f"RESULT: {len(failures)} FAILURE(S)"); sys.exit(1)
print("RESULT: REAL LEARNING WIRING VERIFIED")
