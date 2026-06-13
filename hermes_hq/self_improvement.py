"""Self-improvement and adaptive learning for HQ agents.

This module implements autonomous self-development for agents:
- Performance metrics tracking and analysis
- Automated skill acquisition from mission outcomes
- Agent capability assessment and evolution
- Learning from successes and failures
- Continuous knowledge refinement
- Performance-based agent specialization
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("hermes_hq.self_improvement")


def _self_improvement_dir() -> str:
    """Directory for self-improvement artifacts."""
    try:
        from hermes_constants import get_hermes_home
        base = str(get_hermes_home())
    except Exception:
        base = os.path.expanduser("~/.hermes")
    return os.path.join(base, "hermes_hq", "self_improvement")


def _ensure_dir(path: str) -> None:
    """Create directory if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


@dataclass
class AgentMetric:
    """Performance metric for an agent."""
    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    mission_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentSkill:
    """A learned skill or capability."""
    id: str
    name: str
    description: str
    source_missions: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    usage_count: int = 0
    last_used: Optional[float] = None
    proficiency: float = 0.0  # 0.0 to 1.0
    prerequisites: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class AgentProfile:
    """Adaptive profile tracking agent evolution."""
    agent_id: str
    agent_type: str  # "commander", "specialist", "researcher", etc.
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    # Performance
    total_missions: int = 0
    successful_missions: int = 0
    failed_missions: int = 0
    total_subagent_spawns: int = 0
    avg_mission_duration: float = 0.0
    
    # Learning
    skills: Dict[str, AgentSkill] = field(default_factory=dict)
    learned_patterns: List[Dict[str, Any]] = field(default_factory=list)
    observed_failures: List[Dict[str, Any]] = field(default_factory=list)
    
    # Specialization
    primary_domains: List[str] = field(default_factory=list)
    specialization_score: Dict[str, float] = field(default_factory=dict)
    
    # Metrics
    metrics_history: List[AgentMetric] = field(default_factory=list)
    
    # Adaptations
    adaptations_applied: List[Dict[str, Any]] = field(default_factory=list)


class AgentLearningEngine:
    """Core engine for agent self-improvement."""

    def __init__(self):
        """Initialize the learning engine."""
        self.profiles: Dict[str, AgentProfile] = {}
        self.skills_db: Dict[str, AgentSkill] = {}
        self.patterns_db: List[Dict[str, Any]] = []
        self._lock = __import__("threading").RLock()
        self._load_state()

    def _state_path(self) -> str:
        """Get path to persisted state."""
        dir_path = _self_improvement_dir()
        _ensure_dir(dir_path)
        return os.path.join(dir_path, "learning_state.json")

    def _load_state(self) -> None:
        """Load persisted learning state."""
        path = self._state_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            # Reconstruct profiles
            for agent_id, profile_data in data.get("profiles", {}).items():
                # Reconstruct skills
                skills = {}
                for skill_id, skill_data in profile_data.get("skills", {}).items():
                    skills[skill_id] = AgentSkill(**skill_data)
                profile_data["skills"] = skills
                self.profiles[agent_id] = AgentProfile(**profile_data)
            # Reconstruct skills db
            for skill_id, skill_data in data.get("skills_db", {}).items():
                self.skills_db[skill_id] = AgentSkill(**skill_data)
            self.patterns_db = data.get("patterns_db", [])
            logger.info(f"Loaded learning state for {len(self.profiles)} agents")
        except Exception as e:
            logger.error(f"Failed to load learning state: {e}")

    def _save_state(self) -> None:
        """Persist learning state to disk."""
        path = self._state_path()
        try:
            data = {
                "profiles": {
                    agent_id: {
                        **asdict(profile),
                        "skills": {
                            skill_id: asdict(skill)
                            for skill_id, skill in profile.skills.items()
                        },
                    }
                    for agent_id, profile in self.profiles.items()
                },
                "skills_db": {
                    skill_id: asdict(skill)
                    for skill_id, skill in self.skills_db.items()
                },
                "patterns_db": self.patterns_db,
            }
            temp_path = path + ".tmp"
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            os.replace(temp_path, path)
        except Exception as e:
            logger.error(f"Failed to save learning state: {e}")

    def record_mission_outcome(
        self,
        agent_id: str,
        mission_id: str,
        agent_type: str,
        duration: float,
        success: bool,
        subagent_count: int,
        metrics: Dict[str, float],
        learned_items: List[str],
        failure_reason: Optional[str] = None,
    ) -> None:
        """Record the outcome of a mission for learning."""
        with self._lock:
            profile = self._get_or_create_profile(agent_id, agent_type)
            
            # Update basic metrics
            profile.total_missions += 1
            if success:
                profile.successful_missions += 1
            else:
                profile.failed_missions += 1
            profile.total_subagent_spawns += subagent_count
            profile.avg_mission_duration = (
                (profile.avg_mission_duration * (profile.total_missions - 1) + duration)
                / profile.total_missions
            )
            
            # Record metrics
            for metric_name, value in metrics.items():
                metric = AgentMetric(
                    name=metric_name,
                    value=value,
                    mission_id=mission_id,
                )
                profile.metrics_history.append(metric)
            
            # Extract skills from outcome
            for skill_name in learned_items:
                self._register_skill(profile, skill_name, mission_id, success)
            
            # Record failures for pattern recognition
            if failure_reason:
                profile.observed_failures.append({
                    "mission_id": mission_id,
                    "reason": failure_reason,
                    "timestamp": time.time(),
                })
            
            profile.updated_at = time.time()
            self._save_state()

    def _get_or_create_profile(self, agent_id: str, agent_type: str) -> AgentProfile:
        """Get or create agent profile."""
        if agent_id not in self.profiles:
            self.profiles[agent_id] = AgentProfile(agent_id=agent_id, agent_type=agent_type)
        return self.profiles[agent_id]

    def _register_skill(
        self,
        profile: AgentProfile,
        skill_name: str,
        mission_id: str,
        success: bool,
    ) -> None:
        """Register a skill for an agent."""
        skill_id = f"{profile.agent_id}:{skill_name}"
        
        if skill_id in profile.skills:
            skill = profile.skills[skill_id]
            skill.usage_count += 1
            skill.last_used = time.time()
            if success:
                skill.success_rate = (
                    (skill.success_rate * (skill.usage_count - 1) + 1.0)
                    / skill.usage_count
                )
                skill.proficiency = min(1.0, skill.proficiency + 0.05)
            else:
                skill.proficiency = max(0.0, skill.proficiency - 0.02)
        else:
            skill = AgentSkill(
                id=skill_id,
                name=skill_name,
                description=f"Skill: {skill_name}",
                source_missions=[mission_id],
                success_rate=1.0 if success else 0.0,
                usage_count=1,
                proficiency=0.6 if success else 0.3,
            )
            profile.skills[skill_id] = skill
        
        skill.updated_at = time.time()
        if mission_id not in skill.source_missions:
            skill.source_missions.append(mission_id)

    def get_profile(self, agent_id: str) -> Optional[AgentProfile]:
        """Get an agent's profile."""
        with self._lock:
            return self.profiles.get(agent_id)

    def get_top_skills(
        self, agent_id: str, limit: int = 5
    ) -> List[AgentSkill]:
        """Get an agent's top skills by proficiency."""
        with self._lock:
            profile = self.profiles.get(agent_id)
            if not profile:
                return []
            skills = list(profile.skills.values())
            return sorted(
                skills, key=lambda s: (s.proficiency, s.success_rate), reverse=True
            )[:limit]

    def get_recommendations(self, agent_id: str) -> Dict[str, Any]:
        """Get improvement recommendations for an agent."""
        with self._lock:
            profile = self.profiles.get(agent_id)
            if not profile:
                return {}
            
            recommendations = {
                "optimizations": [],
                "new_skills": [],
                "specializations": [],
                "failure_patterns": [],
            }
            
            # Success rate analysis
            if profile.total_missions > 0:
                success_rate = profile.successful_missions / profile.total_missions
                if success_rate < 0.7:
                    recommendations["optimizations"].append({
                        "type": "low_success_rate",
                        "current": success_rate,
                        "target": 0.85,
                        "suggestion": "Review failure patterns and adjust approach",
                    })
            
            # Skill gaps
            top_skills = self.get_top_skills(agent_id, limit=10)
            if len(top_skills) < 3:
                recommendations["new_skills"].append({
                    "suggestion": "Agent could benefit from wider skill diversity",
                    "related_domains": self._infer_domains(profile),
                })
            
            # Pattern analysis
            failures = profile.observed_failures[-5:] if profile.observed_failures else []
            if failures:
                failure_types = {}
                for f in failures:
                    reason = f.get("reason", "unknown")
                    failure_types[reason] = failure_types.get(reason, 0) + 1
                recommendations["failure_patterns"] = [
                    {"pattern": k, "count": v} for k, v in failure_types.items()
                ]
            
            return recommendations

    def _infer_domains(self, profile: AgentProfile) -> List[str]:
        """Infer potential domains based on agent type."""
        type_to_domains = {
            "commander": ["planning", "delegation", "coordination"],
            "researcher": ["information_gathering", "analysis", "synthesis"],
            "writer": ["content_creation", "editing", "formatting"],
            "engineer": ["debugging", "optimization", "implementation"],
            "analyst": ["data_analysis", "visualization", "reporting"],
        }
        return type_to_domains.get(profile.agent_type, ["general"])

    def detect_specialization(self, agent_id: str) -> Dict[str, float]:
        """Detect the agent's emerging specialization."""
        with self._lock:
            profile = self.profiles.get(agent_id)
            if not profile:
                return {}
            
            if not profile.skills:
                return {}
            
            domain_scores: Dict[str, float] = {}
            for skill in profile.skills.values():
                for tag in skill.tags:
                    if tag not in domain_scores:
                        domain_scores[tag] = 0.0
                    domain_scores[tag] += skill.proficiency
            
            # Normalize and return top specializations
            if domain_scores:
                max_score = max(domain_scores.values())
                if max_score > 0:
                    domain_scores = {
                        k: v / max_score for k, v in domain_scores.items()
                    }
            
            profile.specialization_score = domain_scores
            return domain_scores

    def get_ecosystem_health(self) -> Dict[str, Any]:
        """Analyze overall ecosystem health."""
        with self._lock:
            if not self.profiles:
                return {"status": "empty"}
            
            total_missions = sum(p.total_missions for p in self.profiles.values())
            total_successes = sum(p.successful_missions for p in self.profiles.values())
            avg_success_rate = (
                total_successes / total_missions if total_missions > 0 else 0.0
            )
            
            agent_health = {}
            for agent_id, profile in self.profiles.items():
                health_score = (
                    (profile.successful_missions / max(1, profile.total_missions)) * 0.5
                    + (1.0 - (profile.failed_missions / max(1, profile.total_missions))) * 0.3
                    + (len(profile.skills) / max(1, 20)) * 0.2
                )
                agent_health[agent_id] = {
                    "health_score": min(1.0, health_score),
                    "type": profile.agent_type,
                    "missions": profile.total_missions,
                    "success_rate": (
                        profile.successful_missions / max(1, profile.total_missions)
                    ),
                    "skills_count": len(profile.skills),
                }
            
            return {
                "status": "healthy" if avg_success_rate > 0.7 else "degraded",
                "avg_success_rate": avg_success_rate,
                "total_missions": total_missions,
                "total_agents": len(self.profiles),
                "agents": agent_health,
            }

    def recommend_adaptations(self, agent_id: str) -> List[Dict[str, Any]]:
        """Recommend runtime adaptations for an agent."""
        with self._lock:
            profile = self.profiles.get(agent_id)
            if not profile:
                return []
            
            adaptations = []
            recommendations = self.get_recommendations(agent_id)
            
            # Create actionable adaptations
            for opt in recommendations.get("optimizations", []):
                if opt["type"] == "low_success_rate":
                    adaptations.append({
                        "type": "increase_verification",
                        "priority": "high",
                        "description": "Add extra verification step before mission completion",
                    })
                    adaptations.append({
                        "type": "enable_detailed_logging",
                        "priority": "high",
                        "description": "Capture detailed logs for failure analysis",
                    })
            
            # Specialization recommendations
            specialization = self.detect_specialization(agent_id)
            if specialization:
                top_domain = max(specialization.items(), key=lambda x: x[1])
                adaptations.append({
                    "type": "domain_specialization",
                    "domain": top_domain[0],
                    "confidence": top_domain[1],
                    "description": f"Agent appears to specialize in {top_domain[0]}",
                })
            
            return adaptations


class AgentEvolutionManager:
    """Manages agent evolution and growth."""

    def __init__(self, learning_engine: AgentLearningEngine):
        """Initialize evolution manager."""
        self.learning_engine = learning_engine
        self._evolution_history: Dict[str, List[Dict[str, Any]]] = {}

    def evolve_agent_prompt(
        self,
        agent_id: str,
        current_prompt: str,
        recommendations: Dict[str, Any],
    ) -> str:
        """Evolve an agent's system prompt based on performance."""
        profile = self.learning_engine.get_profile(agent_id)
        if not profile:
            return current_prompt
        
        evolved_prompt = current_prompt
        
        # Add specialization guidance
        specialization = self.learning_engine.detect_specialization(agent_id)
        if specialization:
            top_domain = max(specialization.items(), key=lambda x: x[1])
            evolved_prompt += (
                f"\n\n## Specialization\n"
                f"You have demonstrated expertise in {top_domain[0]}. "
                f"Apply this knowledge when relevant to current tasks."
            )
        
        # Add learned patterns
        if profile.learned_patterns:
            evolved_prompt += "\n\n## Learned Patterns\n"
            for pattern in profile.learned_patterns[-3:]:
                evolved_prompt += f"- {pattern.get('description', '')}\n"
        
        return evolved_prompt

    def create_evolution_summary(self, agent_id: str) -> Dict[str, Any]:
        """Create a summary of agent evolution."""
        profile = self.learning_engine.get_profile(agent_id)
        if not profile:
            return {}
        
        top_skills = self.learning_engine.get_top_skills(agent_id, limit=5)
        specialization = self.learning_engine.detect_specialization(agent_id)
        recommendations = self.learning_engine.get_recommendations(agent_id)
        
        return {
            "agent_id": agent_id,
            "created_at": profile.created_at,
            "total_missions": profile.total_missions,
            "success_rate": (
                profile.successful_missions / max(1, profile.total_missions)
            ),
            "top_skills": [
                {
                    "name": s.name,
                    "proficiency": s.proficiency,
                    "usage_count": s.usage_count,
                }
                for s in top_skills
            ],
            "specialization": specialization,
            "recommendations": recommendations,
        }
