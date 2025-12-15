Based on the research (dependency analysis was successful, web searches hit limits but I have sufficient context from earlier research), I'll now create the comprehensive plan.

---

# Implementation Plan: Ijoka Analytics System

**Type:** Plan
**Status:** Ready
**Created:** 20251213-070000

---

## Overview

Build a comprehensive analytics system for Ijoka that transforms raw observability data into actionable intelligence. The system includes pattern detection using graph algorithms, temporal analytics for productivity insights, agent profiling, an agentic natural language query interface, and a self-improvement feedback loop.

---

## Research Synthesis

### Best Approach
Graph-native analytics using Memgraph's built-in algorithms (community detection, path analysis, PageRank) combined with Python statistical libraries for temporal analysis. The agentic query interface uses LLM-powered Cypher generation with safety validation.

### Libraries/Tools
- **Existing:** neo4j driver, pydantic, fastapi, loguru
- **New:** pandas (time-series), numpy (statistics)
- **Memgraph MAGE:** Community detection, PageRank, path algorithms (no Python dep needed)

### Existing Code to Reuse
- **db.py patterns:** `IjokaClient` class structure, session management, `_node_to_*` converters
- **models.py:** Extend with analytics models (FeatureCluster, WorkflowPattern, etc.)
- **cli.py:** Follow `feature_app` pattern for `analytics_app` command group
- **api.py:** Follow existing endpoint patterns with Pydantic request/response models

### Dependencies
- **Existing:** neo4j≥6.0.3, pydantic≥2.12.5, fastapi≥0.124.4
- **New:** pandas≥2.0.0, numpy≥1.24.0

---

## Plan Structure

```yaml
metadata:
  name: "Ijoka Analytics System"
  created: "20251213-070000"
  status: "ready"

overview: |
  Build analytics modules for pattern detection, temporal analysis, agent profiling,
  and an agentic query interface. Uses graph algorithms and LLM-powered queries.

research:
  approach: "Graph-native analytics with Memgraph MAGE + Python statistical libraries"
  libraries:
    - name: "pandas"
      reason: "Time-series analysis and data transformation"
    - name: "numpy"
      reason: "Statistical computations"
  patterns:
    - file: "db.py:41-98"
      description: "IjokaClient class structure with session management"
    - file: "cli.py:feature_app"
      description: "Typer command group pattern"
    - file: "models.py"
      description: "Pydantic model patterns with enums"
  specifications:
    - requirement: "All analytics via graph queries (Memgraph)"
      status: "must_follow"
    - requirement: "CLI + API + SDK interfaces (DRY)"
      status: "must_follow"
    - requirement: "Agentic queries with safety validation"
      status: "must_follow"
  dependencies:
    existing:
      - "neo4j>=6.0.3"
      - "pydantic>=2.12.5"
      - "fastapi>=0.124.4"
    new:
      - "pandas>=2.0.0"
      - "numpy>=1.24.0"

features:
  - "Pattern Detection Engine"
  - "Temporal Analytics Engine"
  - "Agent Behavior Profiler"
  - "Insight Synthesizer"
  - "Agentic Query Engine"
  - "Self-Improvement Loop"

tasks:
  - id: "task-0"
    name: "Data Model Extensions & Dependencies"
    file: "tasks/task-0.md"
    priority: "blocker"
    dependencies: []

  - id: "task-1"
    name: "Pattern Detection Engine"
    file: "tasks/task-1.md"
    priority: "high"
    dependencies: ["task-0"]

  - id: "task-2"
    name: "Temporal Analytics Engine"
    file: "tasks/task-2.md"
    priority: "high"
    dependencies: ["task-0"]

  - id: "task-3"
    name: "Agent Behavior Profiler"
    file: "tasks/task-3.md"
    priority: "high"
    dependencies: ["task-0"]

  - id: "task-4"
    name: "Insight Synthesizer"
    file: "tasks/task-4.md"
    priority: "medium"
    dependencies: ["task-1", "task-2", "task-3"]

  - id: "task-5"
    name: "Agentic Query Engine"
    file: "tasks/task-5.md"
    priority: "medium"
    dependencies: ["task-4"]

  - id: "task-6"
    name: "CLI & API Integration"
    file: "tasks/task-6.md"
    priority: "medium"
    dependencies: ["task-1", "task-2", "task-3"]

  - id: "task-7"
    name: "Self-Improvement Loop"
    file: "tasks/task-7.md"
    priority: "low"
    dependencies: ["task-5", "task-6"]

shared_resources:
  files:
    - path: "src/ijoka/models.py"
      reason: "All tasks add new models"
      mitigation: "Task 0 creates all base models first"
    - path: "src/ijoka/db.py"
      reason: "Multiple tasks add methods"
      mitigation: "Each task adds to different section"
    - path: "pyproject.toml"
      reason: "Task 0 adds dependencies"
      mitigation: "Only task-0 modifies"

  databases:
    - name: "Memgraph"
      concern: "New node types and relationships"
      mitigation: "Task 0 defines all schema extensions upfront"

testing:
  unit:
    - "Each task writes own tests in tests/test_analytics_*.py"
    - "Mock graph database for unit tests"
  integration:
    - "Test against real Memgraph instance"
    - "Test CLI commands end-to-end"
  isolation:
    - "Each module has independent test file"
    - "Use test fixtures for sample data"

success_criteria:
  - "All 6 analytics modules implemented"
  - "CLI commands: ijoka analytics {patterns,velocity,profile,ask}"
  - "API endpoints: /analytics/*"
  - "Natural language queries work for common questions"
  - "All tests passing"
  - "Documentation updated"

notes: |
  - Tasks 1, 2, 3 can run in PARALLEL after task-0 completes
  - Task 6 can start as soon as any of tasks 1-3 complete
  - Agentic query engine (task-5) is the crown jewel - prioritize after core analytics
  - Self-improvement (task-7) needs data accumulation - lower priority initially

changelog:
  - timestamp: "20251213-070000"
    event: "Plan created"
```

---

## Task Details

### Task 0: Data Model Extensions & Dependencies

```yaml
---
id: task-0
priority: blocker
status: pending
dependencies: []
labels:
  - parallel-execution
  - foundation
  - priority-blocker
---
```

# Data Model Extensions & Dependencies

## 🎯 Objective

Add new Pydantic models for analytics outputs and extend the graph schema. Add pandas/numpy dependencies.

## 🛠️ Implementation Approach

Extend existing models.py with analytics-specific models. Create new graph node types for analytics outputs.

**Libraries:**
- `pandas>=2.0.0` - Time-series analysis
- `numpy>=1.24.0` - Statistical computations

**Pattern to follow:**
- **File:** `models.py:75-102` - Feature model pattern
- **Description:** Pydantic BaseModel with Field defaults, enums for status/type

## 📁 Files to Touch

**Modify:**
- `src/ijoka/models.py` - Add analytics models
- `pyproject.toml` - Add pandas, numpy dependencies

## 🧪 Tests Required

**Unit:**
- [ ] Test model serialization/deserialization
- [ ] Test enum values

## ✅ Acceptance Criteria

- [ ] New models: FeatureCluster, WorkflowPattern, Bottleneck, AgentProfile, VelocityMetrics, AnalyticsInsight
- [ ] Dependencies installed: pandas, numpy
- [ ] Models have proper validation

## 📝 Implementation Details

```python
# New models to add to models.py

class FeatureCluster(BaseModel):
    """Group of related features."""
    id: str
    name: str
    feature_ids: list[str]
    common_category: Optional[FeatureCategory] = None
    avg_completion_time: Optional[float] = None  # hours

class WorkflowPattern(BaseModel):
    """Recurring workflow sequence."""
    id: str
    sequence: list[str]  # tool names or step types
    frequency: int
    avg_duration: Optional[float] = None
    success_rate: Optional[float] = None

class Bottleneck(BaseModel):
    """Identified bottleneck in workflow."""
    id: str
    feature_id: str
    step_description: Optional[str] = None
    severity: str  # low, medium, high, critical
    avg_block_duration: Optional[float] = None  # hours
    occurrences: int = 1

class AgentProfile(BaseModel):
    """Behavioral profile for an agent."""
    agent_id: str
    total_features: int = 0
    completed_features: int = 0
    avg_completion_time: Optional[float] = None
    preferred_categories: list[FeatureCategory] = Field(default_factory=list)
    success_rate: Optional[float] = None
    common_tools: list[str] = Field(default_factory=list)

class VelocityMetrics(BaseModel):
    """Productivity velocity over time."""
    period_start: datetime
    period_end: datetime
    features_completed: int
    features_started: int
    avg_cycle_time: Optional[float] = None  # hours
    trend: str = "stable"  # improving, stable, declining

class AnalyticsInsight(BaseModel):
    """Generated insight from analytics."""
    id: str
    insight_type: str  # pattern, bottleneck, recommendation, anomaly
    description: str
    impact_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    related_features: list[str] = Field(default_factory=list)
    actionable: bool = True
    created_at: Optional[datetime] = None
```

---

### Task 1: Pattern Detection Engine

```yaml
---
id: task-1
priority: high
status: pending
dependencies:
  - task-0
labels:
  - parallel-execution
  - core-analytics
  - priority-high
---
```

# Pattern Detection Engine

## 🎯 Objective

Implement graph-based pattern detection using Memgraph algorithms: community detection, path analysis, bottleneck identification.

## 🛠️ Implementation Approach

Create `PatternDetector` class in new `analytics.py` module. Use Cypher queries with Memgraph's built-in algorithms.

**Pattern to follow:**
- **File:** `db.py:167-212` - list_features query pattern
- **Description:** Session context manager, parameterized Cypher, result mapping

## 📁 Files to Touch

**Create:**
- `src/ijoka/analytics.py` - New analytics module

**Modify:**
- `src/ijoka/db.py` - Add pattern detection methods to IjokaClient

## 🧪 Tests Required

**Unit:**
- [ ] Test cluster detection with mock data
- [ ] Test path analysis returns valid sequences
- [ ] Test bottleneck severity calculation

## ✅ Acceptance Criteria

- [ ] `detect_feature_clusters()` groups features by similarity
- [ ] `find_common_workflows()` identifies recurring sequences
- [ ] `detect_bottlenecks()` finds blocking features/steps
- [ ] All methods return proper Pydantic models

## 📝 Implementation Details

```python
# Add to db.py or new analytics.py

class PatternDetector:
    def __init__(self, client: IjokaClient):
        self.client = client
    
    def detect_feature_clusters(self) -> list[FeatureCluster]:
        """Group features by category and completion patterns."""
        with self.client.session() as session:
            # Simple clustering by category + status patterns
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WITH f.category as category, collect(f) as features
                WHERE size(features) > 1
                RETURN category, 
                       [feat IN features | feat.id] as feature_ids,
                       size(features) as count
                ORDER BY count DESC
            """, path=self.client._project_path)
            # ... map to FeatureCluster models
    
    def find_common_workflows(self, min_frequency: int = 2) -> list[WorkflowPattern]:
        """Find recurring step/tool sequences."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (s:Step)-[:BELONGS_TO]->(f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WITH f, s ORDER BY s.step_order
                WITH f, collect(s.description) as steps
                WITH steps, count(*) as freq
                WHERE freq >= $min_freq
                RETURN steps, freq
                ORDER BY freq DESC
                LIMIT 20
            """, path=self.client._project_path, min_freq=min_frequency)
            # ... map to WorkflowPattern models
    
    def detect_bottlenecks(self) -> list[Bottleneck]:
        """Find features/steps that frequently block progress."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature {status: 'blocked'})-[:BELONGS_TO]->(p:Project {path: $path})
                RETURN f.id as feature_id, 
                       f.description as description,
                       f.block_reason as reason,
                       duration.between(f.updated_at, datetime()).hours as hours_blocked
                ORDER BY hours_blocked DESC
            """, path=self.client._project_path)
            # ... map to Bottleneck models
```

---

### Task 2: Temporal Analytics Engine

```yaml
---
id: task-2
priority: high
status: pending
dependencies:
  - task-0
labels:
  - parallel-execution
  - core-analytics
  - priority-high
---
```

# Temporal Analytics Engine

## 🎯 Objective

Implement time-series analysis for velocity tracking, burndown charts, and productivity patterns.

## 🛠️ Implementation Approach

Create `TemporalAnalyzer` class using pandas for time-series aggregation. Query completion timestamps from graph, analyze with pandas.

**Libraries:**
- `pandas` - DataFrame operations, time-series groupby

**Pattern to follow:**
- **File:** `db.py:483-513` - get_stats aggregation pattern

## 📁 Files to Touch

**Modify:**
- `src/ijoka/analytics.py` - Add TemporalAnalyzer class

## 🧪 Tests Required

**Unit:**
- [ ] Test velocity calculation with known data
- [ ] Test trend detection (improving/stable/declining)
- [ ] Test empty data handling

## ✅ Acceptance Criteria

- [ ] `compute_velocity(window_days)` returns features/day metrics
- [ ] `detect_velocity_drift()` alerts on significant changes
- [ ] `get_productivity_by_period()` shows time-of-day patterns

## 📝 Implementation Details

```python
import pandas as pd
from datetime import datetime, timedelta

class TemporalAnalyzer:
    def __init__(self, client: IjokaClient):
        self.client = client
    
    def compute_velocity(self, window_days: int = 7) -> VelocityMetrics:
        """Calculate feature completion velocity."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.completed_at IS NOT NULL
                  AND f.completed_at > datetime() - duration({days: $days})
                RETURN f.completed_at as completed, f.created_at as created
            """, path=self.client._project_path, days=window_days)
            
            records = list(result)
            if not records:
                return VelocityMetrics(
                    period_start=datetime.now() - timedelta(days=window_days),
                    period_end=datetime.now(),
                    features_completed=0,
                    features_started=0,
                    trend="stable"
                )
            
            # Convert to pandas for analysis
            df = pd.DataFrame([dict(r) for r in records])
            # Calculate metrics...
    
    def detect_velocity_drift(self, threshold: float = 0.3) -> list[str]:
        """Detect significant velocity changes."""
        current = self.compute_velocity(window_days=7)
        previous = self.compute_velocity(window_days=14)  # Compare to prior period
        
        warnings = []
        if previous.features_completed > 0:
            change = (current.features_completed - previous.features_completed) / previous.features_completed
            if abs(change) > threshold:
                warnings.append(f"Velocity changed by {change:.0%} vs previous period")
        return warnings
```

---

### Task 3: Agent Behavior Profiler

```yaml
---
id: task-3
priority: high
status: pending
dependencies:
  - task-0
labels:
  - parallel-execution
  - core-analytics
  - priority-high
---
```

# Agent Behavior Profiler

## 🎯 Objective

Build behavioral profiles for agents showing strengths, weaknesses, and patterns.

## 🛠️ Implementation Approach

Create `AgentProfiler` class that aggregates agent activity from sessions and features.

**Pattern to follow:**
- **File:** `db.py:630-654` - get_active_session pattern

## 📁 Files to Touch

**Modify:**
- `src/ijoka/analytics.py` - Add AgentProfiler class

## 🧪 Tests Required

**Unit:**
- [ ] Test profile generation with mock agent data
- [ ] Test success rate calculation
- [ ] Test category preference detection

## ✅ Acceptance Criteria

- [ ] `build_profile(agent_id)` returns comprehensive AgentProfile
- [ ] `compare_agents(agent_ids)` enables side-by-side comparison
- [ ] `recommend_assignment(feature)` suggests best agent for a task

## 📝 Implementation Details

```python
class AgentProfiler:
    def __init__(self, client: IjokaClient):
        self.client = client
    
    def build_profile(self, agent_id: str) -> AgentProfile:
        """Build comprehensive profile for an agent."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.assigned_agent = $agent
                WITH f,
                     CASE WHEN f.status = 'complete' THEN 1 ELSE 0 END as completed
                RETURN count(f) as total,
                       sum(completed) as completed_count,
                       collect(DISTINCT f.category) as categories
            """, path=self.client._project_path, agent=agent_id)
            
            record = result.single()
            if not record:
                return AgentProfile(agent_id=agent_id)
            
            total = record["total"]
            completed = record["completed_count"]
            
            return AgentProfile(
                agent_id=agent_id,
                total_features=total,
                completed_features=completed,
                success_rate=completed / total if total > 0 else None,
                preferred_categories=[FeatureCategory(c) for c in record["categories"][:3]]
            )
    
    def recommend_assignment(self, feature: Feature) -> list[tuple[str, float]]:
        """Recommend agents for a feature based on past performance."""
        # Query agents who succeeded with similar category features
        # Return [(agent_id, score), ...] ranked by fit
```

---

### Task 4: Insight Synthesizer

```yaml
---
id: task-4
priority: medium
status: pending
dependencies:
  - task-1
  - task-2
  - task-3
labels:
  - sequential
  - priority-medium
---
```

# Insight Synthesizer

## 🎯 Objective

Cross-reference findings from pattern, temporal, and profiler modules to generate actionable insights.

## 🛠️ Implementation Approach

Create `InsightSynthesizer` that combines outputs from all analytics modules, ranks by impact, and generates recommendations.

## 📁 Files to Touch

**Modify:**
- `src/ijoka/analytics.py` - Add InsightSynthesizer class

## 🧪 Tests Required

**Unit:**
- [ ] Test insight ranking algorithm
- [ ] Test recommendation generation
- [ ] Test daily digest format

## ✅ Acceptance Criteria

- [ ] `generate_daily_digest()` returns top insights from last 24h
- [ ] `recommend_actions()` provides prioritized actionable recommendations
- [ ] Insights are persisted to graph for tracking

## 📝 Implementation Details

```python
class InsightSynthesizer:
    def __init__(self, client: IjokaClient):
        self.client = client
        self.pattern_detector = PatternDetector(client)
        self.temporal_analyzer = TemporalAnalyzer(client)
        self.agent_profiler = AgentProfiler(client)
    
    def generate_daily_digest(self) -> list[AnalyticsInsight]:
        """Generate top insights from all modules."""
        insights = []
        
        # From patterns
        bottlenecks = self.pattern_detector.detect_bottlenecks()
        for b in bottlenecks[:3]:
            insights.append(AnalyticsInsight(
                id=str(uuid.uuid4()),
                insight_type="bottleneck",
                description=f"Feature '{b.feature_id[:8]}' blocked: {b.severity} severity",
                impact_score=0.8 if b.severity == "critical" else 0.5,
                confidence=0.9,
                related_features=[b.feature_id],
                actionable=True
            ))
        
        # From velocity
        drift_warnings = self.temporal_analyzer.detect_velocity_drift()
        for warning in drift_warnings:
            insights.append(AnalyticsInsight(
                id=str(uuid.uuid4()),
                insight_type="anomaly",
                description=warning,
                impact_score=0.6,
                confidence=0.7,
                actionable=True
            ))
        
        # Sort by impact * confidence
        insights.sort(key=lambda i: i.impact_score * i.confidence, reverse=True)
        return insights[:10]
```

---

### Task 5: Agentic Query Engine

```yaml
---
id: task-5
priority: medium
status: pending
dependencies:
  - task-4
labels:
  - sequential
  - agentic
  - priority-medium
---
```

# Agentic Query Engine

## 🎯 Objective

Enable natural language queries against analytics data using LLM-powered Cypher generation.

## 🛠️ Implementation Approach

Create `AgenticQueryEngine` that:
1. Takes natural language query
2. Generates Cypher using LLM (via Claude API or local prompt)
3. Validates query safety (read-only, no mutations)
4. Executes and formats response

**Safety:**
- Only allow MATCH/RETURN queries
- Block CREATE/DELETE/SET
- Whitelist allowed node types

## 📁 Files to Touch

**Create:**
- `src/ijoka/query_engine.py` - Agentic query module

## 🧪 Tests Required

**Unit:**
- [ ] Test query validation (blocks mutations)
- [ ] Test common query patterns
- [ ] Test error handling for invalid queries

## ✅ Acceptance Criteria

- [ ] `query(natural_language)` returns structured results
- [ ] Mutations are blocked with clear error
- [ ] Common questions work: "Why are features slow?", "Show my productivity"

## 📝 Implementation Details

```python
class AgenticQueryEngine:
    """Natural language to Cypher query engine."""
    
    SAFE_QUERY_PATTERN = r"^\s*MATCH\s+.*\s+RETURN\s+"
    BLOCKED_KEYWORDS = ["CREATE", "DELETE", "SET", "REMOVE", "MERGE", "DETACH"]
    
    def __init__(self, client: IjokaClient):
        self.client = client
        self.synthesizer = InsightSynthesizer(client)
    
    def query(self, natural_language: str) -> dict:
        """Execute natural language query."""
        # Step 1: Map to pre-defined query patterns (safer than LLM generation)
        query_type = self._classify_query(natural_language)
        
        if query_type == "velocity":
            metrics = self.synthesizer.temporal_analyzer.compute_velocity()
            return {"type": "velocity", "data": metrics.model_dump()}
        
        elif query_type == "bottlenecks":
            bottlenecks = self.synthesizer.pattern_detector.detect_bottlenecks()
            return {"type": "bottlenecks", "data": [b.model_dump() for b in bottlenecks]}
        
        elif query_type == "profile":
            # Extract agent from query
            agent = self._extract_agent(natural_language) or "claude-code"
            profile = self.synthesizer.agent_profiler.build_profile(agent)
            return {"type": "profile", "data": profile.model_dump()}
        
        else:
            # Fallback: return daily digest
            insights = self.synthesizer.generate_daily_digest()
            return {"type": "insights", "data": [i.model_dump() for i in insights]}
    
    def _classify_query(self, text: str) -> str:
        """Classify query intent."""
        text_lower = text.lower()
        if any(w in text_lower for w in ["velocity", "speed", "productivity", "fast", "slow"]):
            return "velocity"
        if any(w in text_lower for w in ["block", "stuck", "bottleneck", "problem"]):
            return "bottlenecks"
        if any(w in text_lower for w in ["profile", "agent", "who", "performance"]):
            return "profile"
        return "general"
```

---

### Task 6: CLI & API Integration

```yaml
---
id: task-6
priority: medium
status: pending
dependencies:
  - task-1
  - task-2
  - task-3
labels:
  - parallel-ready
  - integration
  - priority-medium
---
```

# CLI & API Integration

## 🎯 Objective

Expose analytics through CLI commands and REST API endpoints.

## 🛠️ Implementation Approach

Follow existing patterns in cli.py and api.py. Create `analytics_app` command group.

**Pattern to follow:**
- **File:** `cli.py:plan_app` - Command group pattern
- **File:** `api.py:/features` - REST endpoint pattern

## 📁 Files to Touch

**Modify:**
- `src/ijoka/cli.py` - Add analytics commands
- `src/ijoka/api.py` - Add analytics endpoints

## 🧪 Tests Required

**Unit:**
- [ ] Test CLI output format (JSON and rich)
- [ ] Test API response schemas

## ✅ Acceptance Criteria

- [ ] CLI: `ijoka analytics patterns`, `velocity`, `profile`, `ask`
- [ ] API: GET `/analytics/patterns`, `/velocity`, `/profile/{agent}`
- [ ] POST `/analytics/query` for natural language

## 📝 Implementation Details

```python
# cli.py additions
analytics_app = typer.Typer(help="Analytics and insights")
app.add_typer(analytics_app, name="analytics")

@analytics_app.command("patterns")
def analytics_patterns(json_output: bool = False):
    """Show discovered patterns and clusters."""
    
@analytics_app.command("velocity")
def analytics_velocity(days: int = 7, json_output: bool = False):
    """Show productivity velocity."""

@analytics_app.command("profile")
def analytics_profile(agent: str = "claude-code", json_output: bool = False):
    """Show agent behavior profile."""

@analytics_app.command("ask")
def analytics_ask(question: str, json_output: bool = False):
    """Ask a natural language question about your data."""

# api.py additions
@app.get("/analytics/patterns", tags=["Analytics"])
@app.get("/analytics/velocity", tags=["Analytics"])
@app.get("/analytics/profile/{agent}", tags=["Analytics"])
@app.post("/analytics/query", tags=["Analytics"])
```

---

### Task 7: Self-Improvement Loop

```yaml
---
id: task-7
priority: low
status: pending
dependencies:
  - task-5
  - task-6
labels:
  - sequential
  - future
  - priority-low
---
```

# Self-Improvement Loop

## 🎯 Objective

Track insight effectiveness and refine recommendations based on outcomes.

## 🛠️ Implementation Approach

Create feedback collection mechanism that tracks whether insights led to improvements.

## 📁 Files to Touch

**Modify:**
- `src/ijoka/analytics.py` - Add SelfImprovementLoop class
- `src/ijoka/cli.py` - Add feedback command
- `src/ijoka/api.py` - Add feedback endpoint

## 🧪 Tests Required

**Unit:**
- [ ] Test feedback recording
- [ ] Test confidence score adjustment

## ✅ Acceptance Criteria

- [ ] `ijoka analytics feedback <insight-id> --helpful/--not-helpful`
- [ ] Feedback influences future insight confidence scores
- [ ] Outcome tracking for validated insights

## 📝 Implementation Details

```python
class SelfImprovementLoop:
    def __init__(self, client: IjokaClient):
        self.client = client
    
    def record_feedback(self, insight_id: str, helpful: bool) -> None:
        """Record user feedback on an insight."""
        with self.client.session(mode="WRITE") as session:
            session.run("""
                MATCH (i:AnalyticsInsight {id: $id})
                SET i.feedback_count = coalesce(i.feedback_count, 0) + 1,
                    i.helpful_count = coalesce(i.helpful_count, 0) + $helpful
            """, id=insight_id, helpful=1 if helpful else 0)
    
    def get_insight_effectiveness(self) -> dict:
        """Calculate effectiveness of different insight types."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (i:AnalyticsInsight)
                WHERE i.feedback_count > 0
                RETURN i.insight_type as type,
                       avg(toFloat(i.helpful_count) / i.feedback_count) as effectiveness
            """)
            return {r["type"]: r["effectiveness"] for r in result}
```

---

## Execution Dependency Graph

```
task-0 (Blocker)
   │
   ├──────────────────┬──────────────────┐
   ▼                  ▼                  ▼
task-1 (High)     task-2 (High)     task-3 (High)
[Patterns]        [Temporal]         [Profiler]
   │                  │                  │
   │                  │                  │
   ├──────────────────┴──────────────────┤
   │                                     │
   ▼                                     ▼
task-4 (Medium)                    task-6 (Medium)
[Synthesizer]                      [CLI/API]
   │
   ▼
task-5 (Medium)
[Agentic Query]
   │
   ▼
task-7 (Low)
[Self-Improve]
```

---

## References

- [OpenTelemetry AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [Memgraph MAGE Algorithms](https://memgraph.com/)
- [Agentic Analytics Trends](https://blogs.perficient.com/2025/08/13/from-self-service-to-self-driving-how-agentic-ai-will-transform-analytics-in-the-next-3-years/)
- [SuperAGI Self-Improving Agents](https://superagi.com/top-5-agentic-ai-trends-in-2025-from-multi-agent-collaboration-to-self-healing-systems/)

---

📋 **Plan created in extraction-optimized format!**

**Plan Summary:**
- **8 total tasks**
- **3 can run in parallel** (tasks 1, 2, 3 after task-0)
- **5 have dependencies** (sequential after prerequisites)
- **Conflict risk: Low** (task-0 handles all shared resources first)

**Tasks by Priority:**
- **Blocker:** task-0 (Data Model & Dependencies)
- **High:** task-1, task-2, task-3 (Core Analytics - PARALLEL)
- **Medium:** task-4, task-5, task-6 (Integration)
- **Low:** task-7 (Self-Improvement)

**Parallel Execution Strategy:**
```
Phase 1: task-0 (foundation)
Phase 2: task-1 + task-2 + task-3 (3 parallel workers)
Phase 3: task-4 + task-6 (can overlap)
Phase 4: task-5 → task-7 (sequential)
```

**Next Steps:**
1. Review the plan above
2. Request changes if needed
3. Run `/ctx:execute` to extract and start parallel development

Ready to execute?