"""Adaptive agent capabilities and runtime personalization.

Implements dynamic capability management, runtime adaptation, and agent personas.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger("hermes_hq.adaptive")


class CapabilityLevel(Enum):
    """Capability proficiency levels."""
    NOVICE = 1
    INTERMEDIATE = 2
    EXPERT = 3
    MASTER = 4


@dataclass
class Capability:
    """A learnable capability."""
    id: str
    name: str
    category: str
    description: str
    level: int = 1  # 1-4 corresponding to CapabilityLevel
    prerequisites: List[str] = field(default_factory=list)
    unlocked_at: Optional[float] = None
    last_practiced: Optional[float] = None
    practice_count: int = 0


@dataclass
class RuntimeAdaptation:
    """Runtime configuration adjustment."""
    agent_id: str
    adaptation_type: str
    parameters: Dict[str, Any]
    applied_at: float = field(default_factory=time.time)
    effectiveness: float = 0.0


@dataclass
class AgentPersona:
    """Personal agent profile with style and preferences."""
    agent_id: str
    name: str
    role: str
    communication_style: str
    risk_profile: str  # "conservative", "balanced", "aggressive"
    specialization: str
    personality_traits: List[str] = field(default_factory=list)
    creation_date: float = field(default_factory=time.time)


class CapabilityManager:
    """Manages agent capabilities and progression."""

    def __init__(self):
        """Initialize capability manager."""
        self.capabilities: Dict[str, Dict[str, Capability]] = {}
        self._lock = __import__("threading").RLock()
        self._capability_tree = self._build_capability_tree()

    def _build_capability_tree(self) -> Dict[str, List[str]]:
        """Build prerequisite tree for capabilities."""
        return {
            "basic_reasoning": [],
            "advanced_reasoning": ["basic_reasoning"],
            "risk_assessment": ["basic_reasoning"],
            "optimization": ["advanced_reasoning"],
            "multi_task_coordination": ["advanced_reasoning"],
            "error_recovery": ["basic_reasoning", "risk_assessment"],
            "learning_from_feedback": ["basic_reasoning"],
            "strategic_planning": ["advanced_reasoning", "multi_task_coordination"],
            "creative_problem_solving": ["advanced_reasoning", "optimization"],
        }

    def register_capability(
        self,
        agent_id: str,
        capability_name: str,
        category: str,
        description: str,
        prerequisites: Optional[List[str]] = None,
    ) -> Capability:
        """Register a new capability."""
        with self._lock:
            if agent_id not in self.capabilities:
                self.capabilities[agent_id] = {}
            
            cap_id = f"{agent_id}:{capability_name}"
            capability = Capability(
                id=cap_id,
                name=capability_name,
                category=category,
                description=description,
                prerequisites=(prerequisites or []),
            )
            self.capabilities[agent_id][capability_name] = capability
            return capability

    def unlock_capability(
        self, agent_id: str, capability_name: str
    ) -> bool:
        """Unlock a capability for an agent."""
        with self._lock:
            if agent_id not in self.capabilities:
                return False
            
            if capability_name not in self.capabilities[agent_id]:
                return False
            
            cap = self.capabilities[agent_id][capability_name]
            
            # Check prerequisites
            for prereq in cap.prerequisites:
                if prereq not in self.capabilities[agent_id]:
                    return False
                if self.capabilities[agent_id][prereq].unlocked_at is None:
                    return False
            
            cap.unlocked_at = time.time()
            cap.level = 2  # Upgrade to intermediate
            return True

    def practice_capability(
        self, agent_id: str, capability_name: str, success: bool
    ) -> None:
        """Record capability practice."""
        with self._lock:
            if agent_id not in self.capabilities:
                return
            
            if capability_name not in self.capabilities[agent_id]:
                return
            
            cap = self.capabilities[agent_id][capability_name]
            cap.practice_count += 1
            cap.last_practiced = time.time()
            
            # Level up on successful practice
            if success and cap.practice_count % 5 == 0:
                if cap.level < 4:
                    cap.level += 1

    def get_agent_capabilities(self, agent_id: str) -> Dict[str, Capability]:
        """Get all capabilities for an agent."""
        with self._lock:
            return self.capabilities.get(agent_id, {}).copy()

    def suggest_next_capabilities(self, agent_id: str) -> List[str]:
        """Suggest next capabilities to unlock."""
        with self._lock:
            agent_caps = self.capabilities.get(agent_id, {})
            suggestions = []
            
            for cap_name, cap in agent_caps.items():
                if cap.unlocked_at is None:
                    # Check if prerequisites are met
                    prereqs_met = all(
                        agent_caps.get(p) and agent_caps[p].unlocked_at
                        for p in cap.prerequisites
                    )
                    if prereqs_met:
                        suggestions.append(cap_name)
            
            return suggestions


class RuntimeAdaptationEngine:
    """Adapts agent runtime behavior based on performance."""

    def __init__(self):
        """Initialize adaptation engine."""
        self.adaptations: Dict[str, List[RuntimeAdaptation]] = {}
        self._lock = __import__("threading").RLock()

    def apply_adaptation(
        self,
        agent_id: str,
        adaptation_type: str,
        parameters: Dict[str, Any],
    ) -> RuntimeAdaptation:
        """Apply a runtime adaptation."""
        with self._lock:
            adaptation = RuntimeAdaptation(
                agent_id=agent_id,
                adaptation_type=adaptation_type,
                parameters=parameters,
            )
            
            if agent_id not in self.adaptations:
                self.adaptations[agent_id] = []
            
            self.adaptations[agent_id].append(adaptation)
            return adaptation

    def get_active_adaptations(self, agent_id: str) -> List[RuntimeAdaptation]:
        """Get currently active adaptations."""
        with self._lock:
            return self.adaptations.get(agent_id, []).copy()

    def update_adaptation_effectiveness(
        self,
        agent_id: str,
        adaptation_type: str,
        effectiveness: float,
    ) -> None:
        """Update effectiveness score for an adaptation."""
        with self._lock:
            if agent_id not in self.adaptations:
                return
            
            for adaptation in self.adaptations[agent_id]:
                if adaptation.adaptation_type == adaptation_type:
                    adaptation.effectiveness = effectiveness

    def recommend_adaptations(
        self,
        agent_profile: Any,
        performance_metrics: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """Recommend adaptations based on performance."""
        recommendations = []
        
        # Low success rate adaptations
        if performance_metrics.get("success_rate", 1.0) < 0.7:
            recommendations.append({
                "type": "increase_verification_steps",
                "priority": "high",
                "parameters": {
                    "verification_threshold": 0.95,
                    "double_check_enabled": True,
                },
                "rationale": "Low success rate detected",
            })
        
        # High latency adaptations
        if performance_metrics.get("avg_latency", 0) > 5000:  # 5 seconds
            recommendations.append({
                "type": "enable_caching",
                "priority": "medium",
                "parameters": {
                    "cache_ttl": 3600,
                    "cache_enabled": True,
                },
                "rationale": "High latency detected",
            })
        
        # Resource-constrained adaptations
        if performance_metrics.get("resource_usage", 0) > 0.8:
            recommendations.append({
                "type": "enable_throttling",
                "priority": "high",
                "parameters": {
                    "request_rate_limit": 10,
                    "batch_size": 5,
                },
                "rationale": "High resource usage",
            })
        
        # Low utilization adaptations
        if agent_profile.total_missions > 10 and agent_profile.failed_missions == 0:
            recommendations.append({
                "type": "increase_complexity",
                "priority": "medium",
                "parameters": {
                    "complexity_level": "advanced",
                    "allow_parallel_tasks": True,
                },
                "rationale": "Agent performing well, increase challenge",
            })
        
        return recommendations


class PersonaGenerator:
    """Generates and manages agent personas."""

    def __init__(self):
        """Initialize persona generator."""
        self.personas: Dict[str, AgentPersona] = {}
        self._lock = __import__("threading").RLock()

    def generate_persona(
        self,
        agent_id: str,
        agent_type: str,
        performance_profile: Any,
    ) -> AgentPersona:
        """Generate a persona based on agent type and performance."""
        with self._lock:
            # Determine communication style from type
            style_map = {
                "commander": "authoritative",
                "researcher": "analytical",
                "writer": "expressive",
                "engineer": "pragmatic",
                "analyst": "detailed",
            }
            
            # Determine risk profile from success rate
            if performance_profile.total_missions == 0:
                risk_profile = "balanced"
            else:
                success_rate = (
                    performance_profile.successful_missions
                    / performance_profile.total_missions
                )
                if success_rate > 0.85:
                    risk_profile = "aggressive"
                elif success_rate > 0.7:
                    risk_profile = "balanced"
                else:
                    risk_profile = "conservative"
            
            # Generate personality traits based on skills
            traits = self._infer_traits(performance_profile)
            
            persona = AgentPersona(
                agent_id=agent_id,
                name=f"{agent_type.title()}_{agent_id[:8]}",
                role=agent_type,
                communication_style=style_map.get(agent_type, "neutral"),
                risk_profile=risk_profile,
                specialization=self._infer_specialization(performance_profile),
                personality_traits=traits,
            )
            
            self.personas[agent_id] = persona
            return persona

    def _infer_traits(self, profile: Any) -> List[str]:
        """Infer personality traits."""
        traits = []
        
        if profile.total_missions > 20:
            traits.append("experienced")
        
        if profile.successful_missions / max(1, profile.total_missions) > 0.85:
            traits.append("reliable")
        
        if profile.avg_mission_duration < 60:
            traits.append("efficient")
        
        if len(profile.skills) > 5:
            traits.append("versatile")
        
        return traits

    def _infer_specialization(self, profile: Any) -> str:
        """Infer specialization area."""
        if not profile.skills:
            return "general"
        
        top_skill = max(
            profile.skills.values(),
            key=lambda s: s.proficiency,
        )
        return top_skill.name

    def get_persona(self, agent_id: str) -> Optional[AgentPersona]:
        """Get agent persona."""
        with self._lock:
            return self.personas.get(agent_id)

    def update_persona_style(
        self,
        agent_id: str,
        communication_style: str,
    ) -> None:
        """Update communication style."""
        with self._lock:
            if agent_id in self.personas:
                self.personas[agent_id].communication_style = communication_style

    def list_personas(self) -> List[AgentPersona]:
        """List all agent personas."""
        with self._lock:
            return list(self.personas.values())
