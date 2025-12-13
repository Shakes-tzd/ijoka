"""
Pydantic models for Ijoka domain objects.

These models provide validation, serialization, and rich repr support.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FeatureStatus(str, Enum):
    """Feature lifecycle status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class FeatureCategory(str, Enum):
    """Feature categories for classification."""
    FUNCTIONAL = "functional"
    UI = "ui"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    INFRASTRUCTURE = "infrastructure"
    REFACTORING = "refactoring"
    PLANNING = "planning"
    META = "meta"
    ENHANCEMENT = "enhancement"


class WorkItemType(str, Enum):
    """Work item types for feature classification."""
    FEATURE = "feature"      # New functionality
    BUG = "bug"              # Something broken that needs fixing
    SPIKE = "spike"          # Research/investigation task
    CHORE = "chore"          # Maintenance/cleanup work
    HOTFIX = "hotfix"        # Urgent production fix
    EPIC = "epic"            # Large initiative spanning multiple features


class InsightType(str, Enum):
    """Types of insights that can be recorded."""
    SOLUTION = "solution"
    ANTI_PATTERN = "anti_pattern"
    BEST_PRACTICE = "best_practice"
    TOOL_USAGE = "tool_usage"


class StepStatus(str, Enum):
    """Plan step status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class SessionStatus(str, Enum):
    """Agent session status."""
    ACTIVE = "active"
    ENDED = "ended"
    STALE = "stale"


# =============================================================================
# DOMAIN MODELS
# =============================================================================


class Project(BaseModel):
    """A project being tracked by Ijoka."""
    id: str
    path: str
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Feature(BaseModel):
    """A feature or task being tracked."""
    id: str
    description: str
    category: FeatureCategory
    type: WorkItemType = WorkItemType.FEATURE
    status: FeatureStatus = FeatureStatus.PENDING
    priority: int = Field(default=50, ge=-100, le=100)
    steps: list[str] = Field(default_factory=list)
    work_count: int = Field(default=0, ge=0)

    # Assignment
    assigned_agent: Optional[str] = None
    claiming_session_id: Optional[str] = None
    claiming_agent: Optional[str] = None
    claimed_at: Optional[datetime] = None

    # Blocking
    block_reason: Optional[str] = None

    # Branch affinity
    branch_hint: Optional[str] = None
    file_patterns: list[str] = Field(default_factory=list)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class FeatureListItem(BaseModel):
    """Compact feature representation for list views."""
    id: str
    description: str
    category: FeatureCategory
    type: WorkItemType = WorkItemType.FEATURE
    status: FeatureStatus
    priority: int
    work_count: int = 0
    assigned_agent: Optional[str] = None


class Step(BaseModel):
    """A step in a feature's implementation plan."""
    id: str
    feature_id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    step_order: int = Field(ge=0)
    expected_tools: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Insight(BaseModel):
    """A reusable learning or insight."""
    id: str
    description: str
    pattern_type: InsightType
    tags: list[str] = Field(default_factory=list)
    usage_count: int = Field(default=0, ge=0)
    effectiveness_score: Optional[float] = Field(default=None, ge=0, le=1)
    created_at: Optional[datetime] = None


class Session(BaseModel):
    """An agent session."""
    id: str
    agent: str
    status: SessionStatus = SessionStatus.ACTIVE
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    event_count: int = Field(default=0, ge=0)
    is_subagent: bool = False


class ProjectStats(BaseModel):
    """Statistics about a project's features."""
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    blocked: int = 0
    complete: int = 0
    completion_percentage: int = Field(default=0, ge=0, le=100)


# =============================================================================
# RESPONSE MODELS (for CLI output)
# =============================================================================


class StatusResponse(BaseModel):
    """Response from status command."""
    success: bool = True
    project: Project
    current_feature: Optional[Feature] = None
    stats: ProjectStats
    active_session: Optional[Session] = None
    recent_insights: list[Insight] = Field(default_factory=list)
    active_blockers: list[Feature] = Field(default_factory=list)


class FeatureListResponse(BaseModel):
    """Response from feature list command."""
    success: bool = True
    features: list[FeatureListItem]
    count: int
    stats: ProjectStats


class FeatureResponse(BaseModel):
    """Response from feature operations."""
    success: bool = True
    feature: Feature
    message: Optional[str] = None


class PlanResponse(BaseModel):
    """Response from plan operations."""
    success: bool = True
    feature_id: str
    steps: list[Step]
    active_step: Optional[Step] = None
    progress: dict = Field(default_factory=dict)


class InsightListResponse(BaseModel):
    """Response from insight list command."""
    success: bool = True
    insights: list[Insight]
    count: int


class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    error: str
    details: Optional[dict] = None


# =============================================================================
# ANALYTICS MODELS
# =============================================================================


class BottleneckSeverity(str, Enum):
    """Severity levels for bottlenecks."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VelocityTrend(str, Enum):
    """Velocity trend direction."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class FeatureCluster(BaseModel):
    """Group of related features identified by pattern analysis."""
    id: str
    name: str
    feature_ids: list[str] = Field(default_factory=list)
    common_category: Optional[FeatureCategory] = None
    avg_completion_time: Optional[float] = None  # hours
    size: int = Field(default=0, ge=0)


class WorkflowPattern(BaseModel):
    """Recurring workflow sequence detected across features."""
    id: str
    sequence: list[str] = Field(default_factory=list)  # step types or tool names
    frequency: int = Field(default=1, ge=1)
    avg_duration: Optional[float] = None  # hours
    success_rate: Optional[float] = Field(default=None, ge=0, le=1)


class Bottleneck(BaseModel):
    """Identified bottleneck in workflow."""
    id: str
    feature_id: str
    description: Optional[str] = None
    severity: BottleneckSeverity = BottleneckSeverity.MEDIUM
    avg_block_duration: Optional[float] = None  # hours
    occurrences: int = Field(default=1, ge=1)
    block_reason: Optional[str] = None


class AgentProfile(BaseModel):
    """Behavioral profile for an AI agent."""
    agent_id: str
    total_features: int = Field(default=0, ge=0)
    completed_features: int = Field(default=0, ge=0)
    avg_completion_time: Optional[float] = None  # hours
    preferred_categories: list[FeatureCategory] = Field(default_factory=list)
    success_rate: Optional[float] = Field(default=None, ge=0, le=1)
    common_tools: list[str] = Field(default_factory=list)
    active_hours: Optional[dict[str, int]] = None  # hour -> count


class VelocityMetrics(BaseModel):
    """Productivity velocity over a time period."""
    period_start: datetime
    period_end: datetime
    features_completed: int = Field(default=0, ge=0)
    features_started: int = Field(default=0, ge=0)
    avg_cycle_time: Optional[float] = None  # hours from start to complete
    trend: VelocityTrend = VelocityTrend.STABLE
    features_per_day: Optional[float] = None


class AnalyticsInsightType(str, Enum):
    """Types of analytics insights."""
    PATTERN = "pattern"
    BOTTLENECK = "bottleneck"
    RECOMMENDATION = "recommendation"
    ANOMALY = "anomaly"
    TREND = "trend"


class AnalyticsInsight(BaseModel):
    """Generated insight from analytics processing."""
    id: str
    insight_type: AnalyticsInsightType
    description: str
    impact_score: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.5, ge=0, le=1)
    related_features: list[str] = Field(default_factory=list)
    actionable: bool = True
    created_at: Optional[datetime] = None
    # Feedback tracking for self-improvement
    feedback_count: int = Field(default=0, ge=0)
    helpful_count: int = Field(default=0, ge=0)


# =============================================================================
# ANALYTICS RESPONSE MODELS
# =============================================================================


class PatternAnalysisResponse(BaseModel):
    """Response from pattern analysis."""
    success: bool = True
    clusters: list[FeatureCluster] = Field(default_factory=list)
    patterns: list[WorkflowPattern] = Field(default_factory=list)
    bottlenecks: list[Bottleneck] = Field(default_factory=list)


class VelocityResponse(BaseModel):
    """Response from velocity analysis."""
    success: bool = True
    current: VelocityMetrics
    previous: Optional[VelocityMetrics] = None
    drift_warnings: list[str] = Field(default_factory=list)


class AgentProfileResponse(BaseModel):
    """Response from agent profiling."""
    success: bool = True
    profile: AgentProfile
    recommendations: list[str] = Field(default_factory=list)


class AnalyticsQueryResponse(BaseModel):
    """Response from natural language analytics query."""
    success: bool = True
    query_type: str
    data: dict = Field(default_factory=dict)
    insights: list[AnalyticsInsight] = Field(default_factory=list)


class DailyDigestResponse(BaseModel):
    """Response from daily digest generation."""
    success: bool = True
    date: datetime
    top_insights: list[AnalyticsInsight] = Field(default_factory=list)
    velocity: Optional[VelocityMetrics] = None
    active_bottlenecks: list[Bottleneck] = Field(default_factory=list)
