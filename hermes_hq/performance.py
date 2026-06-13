"""Advanced performance analytics and optimization for agents.

Provides detailed performance analysis, trend detection, and optimization suggestions.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger("hermes_hq.performance")


@dataclass
class PerformanceTrend:
    """Performance trend over time."""
    metric_name: str
    current_value: float
    previous_value: float
    trend: str  # "improving", "degrading", "stable"
    change_percent: float
    period_days: int


@dataclass
class PerformanceOutlier:
    """Outlier performance event."""
    mission_id: str
    metric_name: str
    value: float
    expected_range: Tuple[float, float]
    deviation: float
    timestamp: float


class PerformanceAnalyzer:
    """Analyzes agent performance patterns."""

    def __init__(self):
        """Initialize performance analyzer."""
        self._metrics_cache: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._history_limit = 1000

    def record_metric(
        self,
        agent_id: str,
        metric_name: str,
        value: float,
        mission_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a performance metric."""
        key = f"{agent_id}:{metric_name}"
        entry = {
            "timestamp": time.time(),
            "value": value,
            "mission_id": mission_id,
            "context": context or {},
        }
        self._metrics_cache[key].append(entry)
        
        # Maintain history limit
        if len(self._metrics_cache[key]) > self._history_limit:
            self._metrics_cache[key] = self._metrics_cache[key][-self._history_limit:]

    def analyze_trends(
        self, agent_id: str, metric_name: str, window_days: int = 7
    ) -> Optional[PerformanceTrend]:
        """Analyze trend for a specific metric."""
        key = f"{agent_id}:{metric_name}"
        history = self._metrics_cache.get(key, [])
        
        if len(history) < 2:
            return None
        
        now = time.time()
        cutoff = now - (window_days * 86400)
        
        old_values = [h["value"] for h in history if h["timestamp"] < cutoff]
        new_values = [h["value"] for h in history if h["timestamp"] >= cutoff]
        
        if not old_values or not new_values:
            return None
        
        old_avg = sum(old_values) / len(old_values)
        new_avg = sum(new_values) / len(new_values)
        
        if old_avg == 0:
            change_percent = 0.0
        else:
            change_percent = ((new_avg - old_avg) / old_avg) * 100
        
        # Determine trend
        if abs(change_percent) < 5:
            trend = "stable"
        elif change_percent > 0:
            trend = "improving"
        else:
            trend = "degrading"
        
        return PerformanceTrend(
            metric_name=metric_name,
            current_value=new_avg,
            previous_value=old_avg,
            trend=trend,
            change_percent=change_percent,
            period_days=window_days,
        )

    def detect_anomalies(
        self,
        agent_id: str,
        metric_name: str,
        threshold_std_dev: float = 2.0,
    ) -> List[PerformanceOutlier]:
        """Detect anomalies in metric history."""
        key = f"{agent_id}:{metric_name}"
        history = self._metrics_cache.get(key, [])
        
        if len(history) < 3:
            return []
        
        values = [h["value"] for h in history]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5
        
        outliers = []
        for i, entry in enumerate(history):
            deviation = abs(entry["value"] - mean) / max(std_dev, 0.001)
            if deviation > threshold_std_dev:
                outliers.append(PerformanceOutlier(
                    mission_id=entry.get("mission_id", ""),
                    metric_name=metric_name,
                    value=entry["value"],
                    expected_range=(mean - 2 * std_dev, mean + 2 * std_dev),
                    deviation=deviation,
                    timestamp=entry["timestamp"],
                ))
        
        return outliers

    def get_metric_summary(
        self, agent_id: str, metric_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get comprehensive metric summary."""
        key = f"{agent_id}:{metric_name}"
        history = self._metrics_cache.get(key, [])
        
        if not history:
            return None
        
        values = [h["value"] for h in history]
        
        return {
            "metric_name": metric_name,
            "count": len(history),
            "current": values[-1],
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "median": sorted(values)[len(values) // 2],
            "latest_timestamp": history[-1]["timestamp"],
        }


class OptimizationEngine:
    """Generates optimization recommendations."""

    def __init__(self):
        """Initialize optimization engine."""
        self.analyzer = PerformanceAnalyzer()

    def analyze_agent_performance(self, agent_profile: Any) -> Dict[str, Any]:
        """Comprehensive performance analysis."""
        analysis = {
            "efficiency_score": 0.0,
            "bottlenecks": [],
            "opportunities": [],
            "estimated_improvements": [],
        }
        
        # Calculate efficiency based on success rate and speed
        if agent_profile.total_missions > 0:
            success_rate = (
                agent_profile.successful_missions / agent_profile.total_missions
            )
            efficiency = success_rate * 0.8 + (
                1.0 / max(1.0, agent_profile.avg_mission_duration)
            ) * 0.2
            analysis["efficiency_score"] = min(1.0, efficiency)
        
        # Identify bottlenecks
        if agent_profile.failed_missions > agent_profile.total_missions * 0.2:
            analysis["bottlenecks"].append({
                "type": "high_failure_rate",
                "severity": "high",
                "description": f"Agent has {agent_profile.failed_missions} failures",
            })
        
        if agent_profile.avg_mission_duration > 300:
            analysis["bottlenecks"].append({
                "type": "slow_execution",
                "severity": "medium",
                "description": "Average mission duration exceeds 5 minutes",
            })
        
        # Identify opportunities
        if len(agent_profile.skills) > 0:
            analysis["opportunities"].append({
                "type": "leverage_expertise",
                "description": f"Specialize in {len(agent_profile.skills)} identified domains",
            })
        
        if agent_profile.total_missions > 5:
            analysis["opportunities"].append({
                "type": "parallel_execution",
                "description": "Consider parallel mission execution for efficiency",
            })
        
        # Estimate improvements
        analysis["estimated_improvements"] = [
            {
                "type": "failure_reduction",
                "potential_gain": "15-25% improvement in success rate",
                "effort": "medium",
            },
            {
                "type": "skill_deepening",
                "potential_gain": "20% faster execution in specialized areas",
                "effort": "low",
            },
        ]
        
        return analysis

    def get_optimization_priorities(
        self, profiles: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get prioritized optimization tasks for multiple agents."""
        priorities = []
        
        for agent_id, profile in profiles.items():
            if profile.total_missions == 0:
                continue
            
            success_rate = profile.successful_missions / max(1, profile.total_missions)
            
            if success_rate < 0.6:
                priorities.append({
                    "priority": "critical",
                    "agent_id": agent_id,
                    "issue": "Low success rate",
                    "target": "Increase to 85%+",
                    "estimated_impact": "High",
                })
            elif success_rate < 0.8:
                priorities.append({
                    "priority": "high",
                    "agent_id": agent_id,
                    "issue": "Medium success rate",
                    "target": "Increase to 90%",
                    "estimated_impact": "Medium",
                })
        
        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        priorities.sort(key=lambda x: priority_order.get(x["priority"], 4))
        
        return priorities[:10]  # Return top 10


class ExperienceCollector:
    """Collects and synthesizes agent experiences."""

    def __init__(self):
        """Initialize experience collector."""
        self.experiences: List[Dict[str, Any]] = []
        self._lock = __import__("threading").RLock()

    def record_experience(
        self,
        agent_id: str,
        mission_id: str,
        task: str,
        approach: str,
        outcome: str,
        duration: float,
        success: bool,
        insights: List[str],
    ) -> None:
        """Record an agent's experience."""
        with self._lock:
            self.experiences.append({
                "timestamp": time.time(),
                "agent_id": agent_id,
                "mission_id": mission_id,
                "task": task,
                "approach": approach,
                "outcome": outcome,
                "duration": duration,
                "success": success,
                "insights": insights,
            })

    def extract_patterns(self) -> List[Dict[str, Any]]:
        """Extract patterns from accumulated experiences."""
        patterns = []
        
        # Group by task type
        by_task = defaultdict(list)
        for exp in self.experiences:
            by_task[exp["task"]].append(exp)
        
        # Analyze patterns per task
        for task, exps in by_task.items():
            if len(exps) < 2:
                continue
            
            successful = [e for e in exps if e["success"]]
            success_rate = len(successful) / len(exps) if exps else 0
            
            approaches = defaultdict(lambda: {"count": 0, "success_count": 0})
            for exp in exps:
                approach_key = exp.get("approach", "unknown")
                approaches[approach_key]["count"] += 1
                if exp["success"]:
                    approaches[approach_key]["success_count"] += 1
            
            # Find best approach
            best_approach = max(
                approaches.items(),
                key=lambda x: x[1]["success_count"] / max(1, x[1]["count"]),
                default=None,
            )
            
            if best_approach:
                patterns.append({
                    "task": task,
                    "overall_success_rate": success_rate,
                    "best_approach": best_approach[0],
                    "approach_success_rate": (
                        best_approach[1]["success_count"] / best_approach[1]["count"]
                    ),
                    "total_attempts": len(exps),
                    "key_insights": [],
                })
        
        return patterns

    def get_recommended_approaches(self, task: str) -> List[Dict[str, Any]]:
        """Get recommended approaches for a task."""
        relevant = [e for e in self.experiences if e["task"] == task]
        
        if not relevant:
            return []
        
        approaches = defaultdict(lambda: {"count": 0, "success_count": 0, "avg_time": 0.0})
        for exp in relevant:
            approach_key = exp.get("approach", "unknown")
            approaches[approach_key]["count"] += 1
            if exp["success"]:
                approaches[approach_key]["success_count"] += 1
            approaches[approach_key]["avg_time"] += exp.get("duration", 0.0)
        
        # Finalize averages
        for approach in approaches.values():
            if approach["count"] > 0:
                approach["avg_time"] /= approach["count"]
                approach["success_rate"] = approach["success_count"] / approach["count"]
        
        # Sort by success rate, then by speed
        sorted_approaches = sorted(
            [
                {
                    "approach": name,
                    "success_rate": data["success_rate"],
                    "avg_time": data["avg_time"],
                    "usage_count": data["count"],
                }
                for name, data in approaches.items()
            ],
            key=lambda x: (x["success_rate"], -x["avg_time"]),
            reverse=True,
        )
        
        return sorted_approaches
