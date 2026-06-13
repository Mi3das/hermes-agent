"""Seeder for demonstration of self-improvement systems.

Run this to populate HQ with sample agent learning data.
"""

from __future__ import annotations

import random
import sys
import time
from hermes_hq.engine import HQEngine


def seed_agent_learning_data(engine: HQEngine, num_agents: int = 5, missions_per_agent: int = 20) -> None:
    """Populate engine with realistic learning data."""
    
    agent_types = ["researcher", "writer", "engineer", "analyst", "commander"]
    task_types = ["research", "writing", "coding", "analysis", "planning"]
    skill_names = [
        "web_search",
        "data_synthesis",
        "code_generation",
        "documentation",
        "testing",
        "optimization",
        "debugging",
        "architecture",
    ]
    
    print(f"🌱 Seeding {num_agents} agents with {missions_per_agent} missions each...")
    
    # Create agents and simulate missions
    for agent_num in range(1, num_agents + 1):
        agent_id = f"agent-{agent_num:03d}"
        agent_type = agent_types[agent_num % len(agent_types)]
        
        print(f"\n  Agent {agent_id} ({agent_type}):")
        
        # Generate some personas
        persona = engine.persona_generator.generate_persona(
            agent_id,
            agent_type,
            engine.learning_engine._get_or_create_profile(agent_id, agent_type),
        )
        print(f"    Persona: {persona.name} ({persona.communication_style}, {persona.risk_profile})")
        
        # Simulate missions with varied outcomes
        successful_count = 0
        for mission_idx in range(1, missions_per_agent + 1):
            mission_id = f"mission-{agent_num:02d}-{mission_idx:03d}"
            
            # 80% success rate with natural variation
            success = random.random() < 0.8
            duration = random.gauss(120, 45)  # ~2 min avg, 45s std dev
            
            # Select skills learned during mission
            num_skills = random.randint(1, 3)
            learned_skills = random.sample(skill_names, min(num_skills, len(skill_names)))
            
            # Record mission outcome
            engine.learning_engine.record_mission_outcome(
                agent_id=agent_id,
                mission_id=mission_id,
                agent_type=agent_type,
                duration=max(10, duration),  # No negative durations
                success=success,
                subagent_count=random.randint(0, 5),
                metrics={
                    "tokens_used": random.randint(100, 5000),
                    "api_calls": random.randint(1, 20),
                    "cache_hits": random.randint(0, 10),
                },
                learned_items=learned_skills,
                failure_reason="timeout" if not success and random.random() < 0.5 else None,
            )
            
            if success:
                successful_count += 1
        
        # Register capabilities
        core_capabilities = [
            ("basic_reasoning", "reasoning", "Can reason about simple tasks"),
            ("advanced_reasoning", "reasoning", "Can reason about complex multi-step problems"),
        ]
        
        for cap_name, category, desc in core_capabilities:
            engine.capability_manager.register_capability(
                agent_id, cap_name, category, desc
            )
        
        # Unlock some capabilities based on performance
        success_rate = successful_count / missions_per_agent
        if success_rate > 0.6:
            engine.capability_manager.unlock_capability(agent_id, "basic_reasoning")
            if success_rate > 0.8:
                engine.capability_manager.unlock_capability(agent_id, "advanced_reasoning")
        
        # Record some practices
        for cap_name, _, _ in core_capabilities[:1]:
            for _ in range(random.randint(5, 15)):
                engine.capability_manager.practice_capability(
                    agent_id, cap_name, random.random() < success_rate
                )
        
        # Simulate experiences
        for mission_idx in range(1, min(missions_per_agent + 1, 11)):
            mission_id = f"mission-{agent_num:02d}-{mission_idx:03d}"
            task = random.choice(task_types)
            approach = f"approach_{random.randint(1, 3)}"
            success = random.random() < 0.8
            
            engine.experience_collector.record_experience(
                agent_id=agent_id,
                mission_id=mission_id,
                task=task,
                approach=approach,
                outcome="success" if success else "failed",
                duration=random.gauss(120, 45),
                success=success,
                insights=[
                    "Found efficiency opportunity" if success else "Need better approach",
                    "Resource usage was optimal" if random.random() < 0.5 else "",
                ],
            )
        
        success_rate = (successful_count / missions_per_agent) * 100
        specialization = engine.learning_engine.detect_specialization(agent_id)
        top_spec = max(specialization.items(), key=lambda x: x[1]) if specialization else ("none", 0)
        
        print(f"    Missions: {successful_count}/{missions_per_agent} ✓ ({success_rate:.0f}%)")
        print(f"    Specialization: {top_spec[0]} ({top_spec[1]:.1%})")
        print(f"    Skills: {len(engine.learning_engine.get_top_skills(agent_id))}")


def display_ecosystem_summary(engine: HQEngine) -> None:
    """Display ecosystem summary."""
    print("\n" + "=" * 60)
    print("ECOSYSTEM SUMMARY")
    print("=" * 60)
    
    health = engine.learning_engine.get_ecosystem_health()
    print(f"\nOverall Status: {health['status'].upper()}")
    print(f"Success Rate: {health['avg_success_rate']:.1%}")
    print(f"Total Missions: {health['total_missions']}")
    print(f"Total Agents: {health['total_agents']}")
    
    print("\n📊 Agent Performance:")
    for agent_id, agent_health in list(health["agents"].items())[:5]:
        print(f"  {agent_id}:")
        print(f"    Type: {agent_health['type']}")
        print(f"    Health Score: {agent_health['health_score']:.2f}/1.00")
        print(f"    Success Rate: {agent_health['success_rate']:.1%}")
        print(f"    Missions: {agent_health['missions']}")
        print(f"    Skills: {agent_health['skills_count']}")
    
    print("\n🎯 Optimization Priorities:")
    priorities = engine.optimization_engine.get_optimization_priorities(
        engine.learning_engine.profiles
    )
    for priority in priorities[:3]:
        print(f"  [{priority['priority'].upper()}] {priority['agent_id']}: {priority['issue']}")


def display_agent_profile(engine: HQEngine, agent_id: str) -> None:
    """Display detailed agent profile."""
    profile = engine.learning_engine.get_profile(agent_id)
    if not profile:
        print(f"Agent {agent_id} not found")
        return
    
    print(f"\n{'=' * 60}")
    print(f"AGENT PROFILE: {agent_id}")
    print(f"{'=' * 60}")
    
    print(f"\nMetrics:")
    print(f"  Type: {profile.agent_type}")
    print(f"  Missions: {profile.total_missions}")
    print(f"  Success Rate: {profile.successful_missions / max(1, profile.total_missions):.1%}")
    print(f"  Avg Duration: {profile.avg_mission_duration:.1f}s")
    
    print(f"\nTop Skills:")
    for skill in engine.learning_engine.get_top_skills(agent_id, limit=5):
        print(f"  - {skill.name}: {skill.proficiency:.1%} proficiency ({skill.usage_count} uses)")
    
    print(f"\nSpecialization:")
    spec = engine.learning_engine.detect_specialization(agent_id)
    for domain, score in sorted(spec.items(), key=lambda x: x[1], reverse=True)[:3]:
        print(f"  - {domain}: {score:.1%}")
    
    print(f"\nRecommendations:")
    recs = engine.learning_engine.get_recommendations(agent_id)
    if recs.get("optimizations"):
        for opt in recs["optimizations"][:2]:
            print(f"  - {opt['suggestion']} (target: {opt['target']})")
    else:
        print(f"  No optimizations needed - agent performing well!")
    
    print(f"\nPersona:")
    persona = engine.persona_generator.get_persona(agent_id)
    if persona:
        print(f"  Name: {persona.name}")
        print(f"  Style: {persona.communication_style}")
        print(f"  Risk Profile: {persona.risk_profile}")
        print(f"  Traits: {', '.join(persona.personality_traits)}")
    
    print(f"\nCapabilities:")
    caps = engine.capability_manager.get_agent_capabilities(agent_id)
    unlocked = sum(1 for c in caps.values() if c.unlocked_at is not None)
    print(f"  {unlocked}/{len(caps)} unlocked")
    suggested = engine.capability_manager.suggest_next_capabilities(agent_id)
    if suggested:
        print(f"  Next: {', '.join(suggested[:3])}")


def main():
    """Run seeding demonstration.

    WARNING: This writes FAKE/random demo profiles into the SAME
    learning_state.json that the engine now uses to record REAL mission
    outcomes. Running it pollutes real agent stats with demo data. It is
    therefore guarded behind an explicit env flag and refuses to run otherwise.
    """
    import os as _os
    if _os.environ.get("HQ_ALLOW_FAKE_SEED") != "1":
        print(
            "REFUSING TO SEED FAKE DATA.\n\n"
            "Real mission outcomes are now recorded into the learning store by\n"
            "the engine itself (engine._record_learning_outcome). Seeding random\n"
            "demo profiles here would contaminate those real stats.\n\n"
            "If you really want fake demo data (e.g. to preview the UI on a\n"
            "throwaway HERMES_HOME), set HQ_ALLOW_FAKE_SEED=1 explicitly:\n"
            "    HERMES_HOME=/tmp/hq_demo HQ_ALLOW_FAKE_SEED=1 \\\n"
            "        python -m hermes_hq.seed_demo\n"
        )
        return
    print("\n" + "=" * 60)
    print("HERMES HQ - SELF-IMPROVEMENT SYSTEM SEEDER (FAKE DATA)")
    print("=" * 60)
    
    # Initialize engine
    print("\n🚀 Initializing HQ Engine...")
    engine = HQEngine()
    print("✓ Engine ready")
    
    # Seed data
    seed_agent_learning_data(engine, num_agents=5, missions_per_agent=20)
    
    # Display summaries
    display_ecosystem_summary(engine)
    
    # Show a few agent details
    print(f"\n{'=' * 60}")
    print("DETAILED AGENT PROFILES")
    print(f"{'=' * 60}")
    
    for agent_id in list(engine.learning_engine.profiles.keys())[:2]:
        display_agent_profile(engine, agent_id)
    
    print("\n✅ Seeding complete!")
    print(f"\n📊 You can now access:")
    print(f"   - GET /api/ecosystem/health")
    print(f"   - GET /api/agents/{{agent_id}}/profile")
    print(f"   - GET /api/agents/evolution-summary")


if __name__ == "__main__":
    main()
