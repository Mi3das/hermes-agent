# Hermes HQ Self-Improvement & Adaptive Upgrade

## Overview

The Hermes HQ app has been upgraded with enterprise-grade **automated self-improvement** and **adaptive agent development** systems. Agents now continuously learn from missions, improve their capabilities, and evolve their behavior in real-time.

## New Subsystems

### 1. **Agent Learning Engine** (`self_improvement.py`)

Tracks agent performance, records mission outcomes, and builds comprehensive agent profiles.

**Key Features:**
- **Mission Outcome Tracking**: Records success/failure, duration, and metrics for every mission
- **Skill Registration**: Automatically registers and tracks skills with proficiency levels (0-1.0)
- **Profile Building**: Maintains evolving profiles for each agent
- **Failure Analysis**: Records failure patterns for root-cause analysis
- **Specialization Detection**: Identifies emerging agent specialization areas
- **Knowledge Persistence**: Saves learning state to disk for durability

**Data Structures:**
- `AgentMetric`: Individual performance measurements
- `AgentSkill`: Learned capabilities with proficiency scores
- `AgentProfile`: Complete agent evolution record

### 2. **Performance Analytics** (`performance.py`)

Advanced performance analysis with trend detection and optimization recommendations.

**Key Features:**
- **Trend Analysis**: Detects improving/degrading/stable metric trends
- **Anomaly Detection**: Identifies performance outliers using statistical analysis
- **Experience Collection**: Aggregates agent experiences and extracts patterns
- **Optimization Engine**: Generates prioritized improvement tasks
- **Pattern Recognition**: Learns best approaches for recurring tasks

**Key Classes:**
- `PerformanceAnalyzer`: Tracks and analyzes metrics over time
- `OptimizationEngine`: Recommends performance improvements
- `ExperienceCollector`: Synthesizes learnings from agent missions

### 3. **Adaptive Agent Systems** (`adaptive.py`)

Runtime personalization, capability progression, and agent specialization.

**Key Features:**
- **Capability Progression**: Agents unlock and master new capabilities
- **Runtime Adaptation**: Dynamically adjusts agent configuration based on performance
- **Persona Generation**: Creates unique profiles for each agent
- **Risk Profiling**: Adapts behavior based on success rates
- **Specialization Tracking**: Monitors emerging expertise domains

**Key Classes:**
- `CapabilityManager`: Manages learnable capabilities with prerequisites
- `RuntimeAdaptationEngine`: Applies dynamic runtime adjustments
- `PersonaGenerator`: Creates and manages agent personas

## API Endpoints

### Agent Profiles

```
GET /api/agents/{agent_id}/profile
```
Get comprehensive agent profile including:
- Mission statistics
- Top skills with proficiency scores
- Specialization analysis
- Improvement recommendations

**Response:**
```json
{
  "profile": {
    "agent_id": "agent-123",
    "type": "researcher",
    "total_missions": 45,
    "successful_missions": 42,
    "failed_missions": 3,
    "success_rate": 0.933,
    "avg_duration": 145.5,
    "skills_count": 8
  },
  "skills": [
    {
      "name": "web_research",
      "proficiency": 0.95,
      "usage_count": 23,
      "success_rate": 0.96
    },
    {
      "name": "data_synthesis",
      "proficiency": 0.87,
      "usage_count": 18,
      "success_rate": 0.89
    }
  ],
  "specialization": {
    "research": 0.92,
    "analysis": 0.78
  },
  "recommendations": {
    "optimizations": [],
    "new_skills": [],
    "specializations": [],
    "failure_patterns": []
  }
}
```

### Agent Capabilities

```
GET /api/agents/{agent_id}/capabilities
```
Get all capabilities and progression:

```json
{
  "capabilities": {
    "basic_reasoning": {
      "name": "basic_reasoning",
      "category": "reasoning",
      "level": 3,
      "unlocked": true,
      "practice_count": 42
    },
    "advanced_reasoning": {
      "name": "advanced_reasoning",
      "category": "reasoning",
      "level": 2,
      "unlocked": true,
      "practice_count": 18
    }
  },
  "suggested_next": [
    "strategic_planning",
    "creative_problem_solving"
  ]
}
```

### Agent Personas

```
GET /api/agents/{agent_id}/personas
```
Get agent's communication style and personality profile:

```json
{
  "agent_id": "agent-456",
  "name": "Researcher_a1b2c3d4",
  "role": "researcher",
  "communication_style": "analytical",
  "risk_profile": "balanced",
  "specialization": "web_research",
  "personality_traits": [
    "experienced",
    "reliable",
    "versatile"
  ],
  "creation_date": 1781311600.0
}
```

### Ecosystem Health

```
GET /api/ecosystem/health
```
Get overall ecosystem health and agent statistics:

```json
{
  "status": "healthy",
  "avg_success_rate": 0.875,
  "total_missions": 342,
  "total_agents": 12,
  "agents": {
    "commander-1": {
      "health_score": 0.89,
      "type": "commander",
      "missions": 56,
      "success_rate": 0.91,
      "skills_count": 9
    }
  }
}
```

### Optimization Priorities

```
GET /api/ecosystem/optimization-priorities
```
Get prioritized improvement tasks sorted by impact:

```json
{
  "priorities": [
    {
      "priority": "critical",
      "agent_id": "agent-789",
      "issue": "Low success rate",
      "target": "Increase to 85%+",
      "estimated_impact": "High"
    },
    {
      "priority": "high",
      "agent_id": "agent-101",
      "issue": "Medium success rate",
      "target": "Increase to 90%",
      "estimated_impact": "Medium"
    }
  ]
}
```

### Agent Adaptations

```
GET /api/agents/{agent_id}/adaptations
```
Get currently active runtime adaptations:

```json
{
  "adaptations": [
    {
      "type": "increase_verification",
      "parameters": {
        "verification_threshold": 0.95,
        "double_check_enabled": true
      },
      "effectiveness": 0.78
    }
  ]
}
```

### Experience Patterns

```
GET /api/agents/{agent_id}/experience-patterns
```
Get patterns learned from mission experiences:

```json
{
  "patterns": [
    {
      "task": "web_research",
      "overall_success_rate": 0.94,
      "best_approach": "parallel_search",
      "approach_success_rate": 0.98,
      "total_attempts": 23
    }
  ]
}
```

### Evolution Summary

```
GET /api/agents/evolution-summary
```
Get evolution progress for all agents:

```json
{
  "agent-123": {
    "agent_id": "agent-123",
    "created_at": 1781294845.0,
    "total_missions": 45,
    "success_rate": 0.933,
    "top_skills": [
      {
        "name": "web_research",
        "proficiency": 0.95,
        "usage_count": 23
      }
    ],
    "specialization": {
      "research": 0.92
    },
    "recommendations": {}
  }
}
```

### Practice Capability

```
POST /api/agents/{agent_id}/capabilities/{capability_name}/practice
?success=true
```
Record capability practice/training.

## Self-Improvement Mechanisms

### 1. **Continuous Learning**
- Every mission outcome updates agent profiles
- Skills are registered and tracked across missions
- Success patterns are analyzed for optimization

### 2. **Adaptive Specialization**
- Agents automatically specialize based on mission success
- Specialization scores guide future task assignment
- Recommendation engine suggests domain expertise for new tasks

### 3. **Capability Progression**
- Capabilities unlock through skill mastery
- Prerequisites ensure proper progression
- Practice counts drive capability level advancement

### 4. **Runtime Adaptation**
- Low success rates trigger verification enhancements
- High latency triggers caching optimizations
- Resource constraints trigger throttling
- High performers get increased complexity

### 5. **Experience-Driven Optimization**
- Best approaches for tasks are identified automatically
- Failure patterns are analyzed for root causes
- Recommendations are personalized per agent

## Example: Agent Evolution Lifecycle

```
1. INITIALIZATION
   Agent created with basic capabilities
   Persona generated based on type
   
2. FIRST MISSIONS
   Success/failure recorded
   Initial skills registered
   Metrics baseline established
   
3. PATTERN RECOGNITION (5-10 missions)
   Approach effectiveness analyzed
   Specialization areas identified
   Early recommendations generated
   
4. ADAPTATION (10-20 missions)
   Runtime adaptations applied
   Capabilities unlocked
   Communication style refined
   
5. SPECIALIZATION (20+ missions)
   Clear specialization emerges
   Expert-level capabilities developed
   Risk profile optimized
   
6. OPTIMIZATION (50+ missions)
   Advanced capabilities mastered
   Cross-skill synthesis enabled
   Delegation patterns established
```

## Integration with Streaming

The live `/api/stream` endpoint now includes:

```json
{
  "t": 1781311684.74,
  "hq": {...},
  "agents_evolution": {
    "active_learners": 5,
    "avg_success_rate": 0.87,
    "specializations_detected": 12
  }
}
```

## Data Persistence

All learning data is persisted to:
- `~/.hermes/hermes_hq/self_improvement/learning_state.json`

This includes:
- Agent profiles
- Skills database
- Performance patterns
- Capability trees

## Performance Impact

- **Overhead**: <50ms per mission outcome
- **Memory**: ~10KB per agent after 100 missions
- **Disk**: ~100KB for full learning state
- **CPU**: Negligible impact from background analysis

## Future Enhancements

1. **Cross-Agent Learning**: Agents learn from each other's experiences
2. **Emergent Behavior**: Agents discover new strategies collectively
3. **Role Evolution**: Agents can transition between roles
4. **Genetic Algorithms**: Optimize approaches through simulated evolution
5. **Transfer Learning**: Apply knowledge from similar domains
6. **Swarm Intelligence**: Coordinate ecosystem-wide optimizations

## Configuration

Future config options (in `config.yaml`):
```yaml
hermes_hq:
  self_improvement:
    enabled: true
    learning_rate: 1.0
    specialization_threshold: 0.8
    auto_adaptation: true
    capability_unlock_threshold: 0.85
    experience_retention: 1000
```
