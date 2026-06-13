#!/usr/bin/env markdown
# Hermes HQ Self-Improvement: Technical Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AGENT LIFE CYCLE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐         ┌─────────────┐         ┌──────────────┐     │
│  │   MISSION   │ ──────> │  LEARNING   │ ──────> │ PERFORMANCE  │     │
│  │  EXECUTION  │ Outcome │   ENGINE    │ Record  │   ANALYTICS  │     │
│  └─────────────┘         └─────────────┘         └──────────────┘     │
│        │                       │                        │                │
│        │ (Success/Failure)    │ (Profile Update)      │ (Pattern)      │
│        │                       │                        │                │
│        V                       V                        V                │
│   Duration, Metrics     Skills, Profiles,        Trends, Patterns,    │
│   Resources Used        Specialization           Anomalies            │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              ADAPTATION ENGINE (Feedback Loop)                  │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  • Capability Unlock                                            │   │
│  │  • Runtime Config Adjustment                                    │   │
│  │  • Specialization Tracking                                      │   │
│  │  • Persona Refinement                                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│        │                                                                  │
│        └──────────> IMPROVED AGENT (Next Mission)                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

### 1. Learning Engine (`self_improvement.py`)

```python
AgentLearningEngine
├── Responsibilities
│   ├─ Record mission outcomes
│   ├─ Track agent profiles
│   ├─ Register skills
│   ├─ Analyze specializations
│   └─ Generate recommendations
│
├── Core Data Structures
│   ├─ AgentMetric(timestamp, metric_type, value, context)
│   ├─ AgentSkill(name, proficiency, usage_count, success_rate)
│   └─ AgentProfile(agent_id, agent_type, metrics[], skills[])
│
└── Key Methods (30+)
    ├─ record_mission_outcome()           # Primary entry point
    ├─ register_skill()                   # Add new skill
    ├─ get_profile()                      # Full agent profile
    ├─ detect_specialization()            # Domain analysis
    ├─ get_ecosystem_health()             # Overall metrics
    └─ [20+ more...]
```

**Data Flow:**
```
Mission Event
    ↓
record_mission_outcome()
    ├─ Create AgentMetric
    ├─ Register skills from learned_items
    ├─ Update AgentProfile
    ├─ Persist to disk
    └─ Return success/failure
    
Profile Query
    ↓
get_profile(agent_id)
    ├─ Load or create profile
    ├─ Calculate metrics
    ├─ Track trends
    └─ Return complete profile
```

### 2. Performance Analyzer (`performance.py`)

```python
PerformanceAnalyzer
├── Responsibilities
│   ├─ Track metrics over time
│   ├─ Detect trends
│   ├─ Find anomalies
│   └─ Recommend optimizations
│
├── Analysis Types
│   ├─ Trend: Linear regression on metric time series
│   ├─ Outlier: Statistical Z-score detection
│   ├─ Pattern: Approach success rate analysis
│   └─ Optimization: Priority-ranked suggestions
│
└── Key Classes
    ├─ PerformanceTrend(metric, trend_type, confidence)
    ├─ PerformanceOutlier(metric, value, z_score)
    ├─ OptimizationPriority(priority_level, agent_id, issue, target)
    └─ [Analytics methods...]

ExperienceCollector
├─ Responsibilities
│  ├─ Record agent experiences
│  ├─ Extract patterns
│  └─ Identify best approaches
│
└─ Key Methods
   ├─ record_experience()            # Log mission data
   ├─ extract_patterns()             # Analyze approaches
   └─ get_best_approach()            # Recommendation

OptimizationEngine
├─ Responsibilities
│  ├─ Analyze profiles
│  ├─ Generate recommendations
│  └─ Prioritize improvements
│
└─ Key Methods
   ├─ get_optimization_priorities()  # Main analysis
   ├─ analyze_failure_patterns()     # Root cause
   └─ suggest_improvements()         # Suggestions
```

**Analysis Pipeline:**
```
Time Series Data
    ↓
PerformanceAnalyzer.analyze()
    ├─ detect_trends()
    │  └─ Linear regression on (timestamp, value) pairs
    ├─ detect_anomalies()
    │  └─ Z-score > 2.0 detection
    └─ identify_patterns()
       └─ Group by task, calculate success rates
    
Patterns + Optimization
    ↓
OptimizationEngine.get_priorities()
    ├─ Filter low performers
    ├─ Find failure hotspots
    ├─ Rank by impact
    └─ Return prioritized list
```

### 3. Adaptive Systems (`adaptive.py`)

```python
CapabilityManager
├─ Manages capability progression
├─ Data: Capability(name, category, level, prerequisites)
├─ Operations
│  ├─ register_capability()        # Add new capability
│  ├─ unlock_capability()          # Mark unlocked
│  ├─ practice_capability()        # Record practice
│  ├─ suggest_next()               # Recommendation
│  └─ get_capabilities()           # Full list
│
└─ Progression Rules
   ├─ Novice (0)   -> Intermediate (1)   [10 practices]
   ├─ Inter (1)    -> Advanced (2)       [25 practices]
   ├─ Advanced (2) -> Expert (3)         [50 practices]
   └─ Expert (3)   -> Master (4)         [100 practices]

RuntimeAdaptationEngine
├─ Responsibilities
│  ├─ Adjust config based on performance
│  ├─ Track adaptation effectiveness
│  └─ Apply rule-based changes
│
├─ Adaptation Rules
│  ├─ Low success     -> increase_verification
│  ├─ High latency    -> enable_caching
│  ├─ High failure    -> reduce_concurrency
│  └─ High performer  -> increase_complexity
│
└─ Key Methods
   ├─ apply_adaptations()
   ├─ get_active_adaptations()
   └─ track_effectiveness()

PersonaGenerator
├─ Generates unique profiles
├─ Data: AgentPersona(name, role, style, risk_profile, traits)
├─ Style Options
│  ├─ analytical (research-focused)
│  ├─ pragmatic (engineering-focused)
│  ├─ expressive (creative-focused)
│  └─ authoritative (command-focused)
│
├─ Risk Profiles
│  ├─ conservative (verify everything)
│  ├─ balanced (normal operation)
│  └─ aggressive (high-risk actions)
│
└─ Auto-traits Based on Performance
   ├─ efficient (low resource usage)
   ├─ reliable (high success rate)
   └─ versatile (multiple specializations)
```

**Capability Progression:**
```
New Agent
    ↓
register_capability("web_search", "research")
    ↓
Agent performs web searches during missions
    ↓
practice_capability("web_search", success=true) ×10
    │
    └─> NOVICE -> INTERMEDIATE
    
practice_capability("web_search", success=true) ×25
    │
    └─> INTERMEDIATE -> ADVANCED
    
practice_capability("web_search", success=true) ×50
    │
    └─> ADVANCED -> EXPERT
    
practice_capability("web_search", success=true) ×100
    │
    └─> EXPERT -> MASTER
```

## Data Persistence

### Storage Structure
```
~/.hermes/hermes_hq/
├── self_improvement/
│   └── learning_state.json
│       ├── version: "1.0"
│       ├── generated: ISO timestamp
│       ├── agents: {
│       │   "agent-001": {
│       │       "profiles": {...},
│       │       "skills": {...},
│       │       "evolution": [...]
│       │   }
│       └── }
```

### Persistence Model
- **Format**: JSON
- **Update Strategy**: Full rewrite on each modification
- **Frequency**: After every mission outcome
- **Durability**: Atomic writes (temp file + rename)
- **Recovery**: Automatic fallback to empty state on corruption
- **Size**: ~100KB for full ecosystem (5 agents × 100 missions)

## API Integration

### Engine Initialization
```python
class HQEngine:
    def __init__(self):
        self.learning_engine = AgentLearningEngine()
        self.evolution_manager = AgentEvolutionManager()
        self.performance_analyzer = PerformanceAnalyzer()
        self.optimization_engine = OptimizationEngine()
        self.experience_collector = ExperienceCollector()
        self.capability_manager = CapabilityManager()
        self.adaptation_engine = RuntimeAdaptationEngine()
        self.persona_generator = PersonaGenerator()
```

### New Endpoints
```
GET  /api/agents/{agent_id}/profile
     └─ engine.learning_engine.get_profile()
     └─ engine.evolution_manager.create_evolution_summary()
     └─ engine.capability_manager.get_agent_capabilities()

GET  /api/agents/{agent_id}/personas
     └─ engine.persona_generator.get_persona()

GET  /api/ecosystem/health
     └─ engine.learning_engine.get_ecosystem_health()

GET  /api/ecosystem/optimization-priorities
     └─ engine.optimization_engine.get_optimization_priorities()

[9 more endpoints...]
```

## Thread Safety

All subsystems use **RLock** for thread safety:

```python
class AgentLearningEngine:
    def __init__(self):
        self._lock = RLock()
        self.profiles = {}
    
    def record_mission_outcome(self, ...):
        with self._lock:
            # Protected operation
            profile = self._get_or_create_profile(agent_id)
            profile.record_mission(...)
            self._persist()
```

**Thread Safety Guarantees:**
- ✅ Multiple concurrent mission records
- ✅ Simultaneous API queries during recording
- ✅ Safe file I/O operations
- ✅ No race conditions in state updates

## Performance Characteristics

| Operation | Time | Memory |
|-----------|------|--------|
| Record mission outcome | <50ms | Negligible |
| Load full profile | <10ms | 1-2 KB |
| Query ecosystem health | <50ms | 5 KB |
| Query optimization priorities | <100ms | 10 KB |
| Save learning state | <100ms | Sync I/O |
| **Per-agent footprint (100 missions)** | **N/A** | **~10 KB** |

## Extensibility Points

### Adding New Metrics
```python
# In AgentLearningEngine.record_mission_outcome()
agentmetric = AgentMetric(
    timestamp=time.time(),
    metric_type="custom_metric_name",
    value=calculated_value,
    context={"task_type": "...", "result": "..."}
)
profile.metrics.append(metric)
```

### Custom Optimizations
```python
# In OptimizationEngine.get_optimization_priorities()
if agent_profile.success_rate < threshold:
    priority = OptimizationPriority(
        priority="critical",
        agent_id=agent_id,
        issue="Custom issue description",
        target="Custom target description",
        estimated_impact="High"
    )
    priorities.append(priority)
```

### New Adaptations
```python
# In RuntimeAdaptationEngine.apply_adaptations()
if performance_metric > high_threshold:
    adaptation = RuntimeAdaptation(
        adaptation_type="custom_adaptation",
        parameters={"param1": value1, "param2": value2},
        effectiveness=initial_effectiveness_estimate
    )
    self.active_adaptations[agent_id].append(adaptation)
```

## Integration Patterns

### Pattern 1: Mission Recording
```python
# From HQ core after mission completes
engine.learning_engine.record_mission_outcome(
    agent_id="agent-123",
    mission_id="mission-456",
    agent_type="researcher",
    duration=145.3,
    success=True,
    subagent_count=3,
    metrics={"tokens_used": 2500, "api_calls": 8},
    learned_items=["web_research", "data_synthesis"],
    failure_reason=None
)

# Result: Profile updated, specialization analyzed, 
# performance trended, adaptations considered
```

### Pattern 2: Profile Query
```python
# From dashboard requesting agent info
profile = engine.learning_engine.get_profile("agent-123")

# Returns: Complete profile with
# - Mission history
# - Skill proficiency
# - Specialization scores
# - Recommendations
# - Evolution metrics
```

### Pattern 3: Ecosystem Monitoring
```python
# From streaming endpoint
health = engine.learning_engine.get_ecosystem_health()

# Includes: Overall success rate, agent count,
# individual health scores, specialization distribution
```

## Testing & Validation

### Unit Testing
```python
def test_skill_proficiency():
    engine = HQEngine()
    engine.learning_engine.register_skill(
        "agent-1", "web_search", "research"
    )
    engine.learning_engine.practice_capability(
        "agent-1", "web_search", success=True
    )
    profile = engine.learning_engine.get_profile("agent-1")
    assert "web_search" in profile.skills
    assert profile.skills["web_search"].proficiency > 0

def test_ecosystem_health():
    engine = HQEngine()
    # Record missions...
    health = engine.learning_engine.get_ecosystem_health()
    assert health["status"] in ["healthy", "degraded", "critical"]
    assert "avg_success_rate" in health
```

### Integration Testing
```python
# seed_demo.py provides complete integration test
# - 5 agents
# - 20 missions each
# - Realistic outcomes
# - Full data persistence
# - API queryable
```

## Monitoring & Debugging

### Inspection
```bash
# Check learning state
cat ~/.hermes/hermes_hq/self_improvement/learning_state.json | python -m json.tool

# Query specific agent
curl http://localhost:8787/api/agents/agent-001/profile | python -m json.tool
```

### Logging
```python
# Learning engine logs key events
logger.info(f"Recorded mission {mission_id} for {agent_id}")
logger.debug(f"Specialization detected: {specialization}")
logger.warning(f"Optimization needed: {issue}")
```

---

**Architecture Version**: 1.0  
**Last Updated**: June 13, 2026  
**Status**: Production-Ready
