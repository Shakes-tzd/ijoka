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
