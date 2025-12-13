"""
FastAPI server for Ijoka.

Provides HTTP API for remote/multi-agent access to Ijoka features.

Usage:
    # Start server
    ijoka-server
    # or
    uvicorn ijoka.api:app --reload

    # Call endpoints
    curl http://localhost:8000/status
    curl http://localhost:8000/features
    curl -X POST http://localhost:8000/features -d '{"description": "...", "category": "functional"}'
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field

from .analytics import AgentProfiler, InsightSynthesizer, PatternDetector, TemporalAnalyzer
from .db import IjokaClient
from .models import (
    AgentProfileResponse,
    AnalyticsQueryResponse,
    DailyDigestResponse,
    Feature,
    FeatureCategory,
    FeatureListItem,
    FeatureStatus,
    Insight,
    InsightType,
    PatternAnalysisResponse,
    Project,
    ProjectStats,
    Step,
    VelocityResponse,
    WorkItemType,
)
from .query_engine import AgenticQueryEngine


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class CreateFeatureRequest(BaseModel):
    """Request to create a new feature."""
    description: str = Field(..., min_length=1, description="Feature description")
    category: FeatureCategory = Field(..., description="Feature category")
    type: WorkItemType = Field(default=WorkItemType.FEATURE, description="Work item type")
    priority: int = Field(default=50, ge=-100, le=100, description="Priority (higher = more important)")
    steps: Optional[list[str]] = Field(default=None, description="Implementation steps")
    branch_hint: Optional[str] = Field(default=None, description="Git branch hint")
    file_patterns: Optional[list[str]] = Field(default=None, description="File patterns for classification")


class UpdateFeatureRequest(BaseModel):
    """Request to update a feature."""
    description: Optional[str] = Field(default=None, min_length=1)
    category: Optional[FeatureCategory] = None
    priority: Optional[int] = Field(default=None, ge=-100, le=100)


class BlockFeatureRequest(BaseModel):
    """Request to block a feature."""
    reason: str = Field(..., min_length=1, description="Why the feature is blocked")
    blocking_feature_id: Optional[str] = Field(default=None, description="ID of blocking feature")


class RecordInsightRequest(BaseModel):
    """Request to record an insight."""
    description: str = Field(..., min_length=1, description="What was learned")
    pattern_type: InsightType = Field(..., description="Type of insight")
    tags: Optional[list[str]] = Field(default=None, description="Tags for categorization")
    feature_id: Optional[str] = Field(default=None, description="Related feature ID")


class StatusResponse(BaseModel):
    """Response for status endpoint."""
    success: bool = True
    project: Project
    stats: ProjectStats
    current_feature: Optional[Feature] = None


class FeatureListResponse(BaseModel):
    """Response for feature list endpoint."""
    success: bool = True
    features: list[FeatureListItem]
    count: int
    stats: ProjectStats


class FeatureResponse(BaseModel):
    """Response for single feature operations."""
    success: bool = True
    feature: Feature
    message: Optional[str] = None


class InsightListResponse(BaseModel):
    """Response for insight list endpoint."""
    success: bool = True
    insights: list[Insight]
    count: int


class InsightResponse(BaseModel):
    """Response for single insight operations."""
    success: bool = True
    insight: Insight
    message: Optional[str] = None


class MessageResponse(BaseModel):
    """Generic message response."""
    success: bool = True
    message: str


class AnalyticsQueryRequest(BaseModel):
    """Request for natural language analytics query."""
    question: str = Field(..., min_length=1, description="Natural language question")


class SetPlanRequest(BaseModel):
    """Request to set plan for a feature."""
    steps: list[str] = Field(..., min_length=1, description="Ordered list of implementation steps")


class CheckpointRequest(BaseModel):
    """Request to report progress checkpoint."""
    step_completed: Optional[str] = Field(default=None, description="Step just completed")
    current_activity: Optional[str] = Field(default=None, description="Current work")


class DiscoverFeatureRequest(BaseModel):
    """Request to discover and create feature from recent activity."""
    description: str = Field(..., min_length=1)
    category: FeatureCategory
    type: WorkItemType = Field(default=WorkItemType.FEATURE, description="Work item type")
    priority: int = Field(default=50, ge=-100, le=100)
    steps: Optional[list[str]] = None
    lookback_minutes: int = Field(default=60, ge=1)
    mark_complete: bool = False


class PlanResponse(BaseModel):
    """Response for plan operations."""
    success: bool = True
    feature_id: str
    steps: list[dict]  # Step info
    active_step: Optional[dict] = None
    progress: dict
    message: Optional[str] = None


class CheckpointResponse(BaseModel):
    """Response for checkpoint operations."""
    success: bool = True
    feature: Optional[dict] = None
    active_step: Optional[dict] = None
    progress: dict
    warnings: list[str] = Field(default_factory=list)


# =============================================================================
# APP SETUP
# =============================================================================


# Global client - initialized on startup
_client: Optional[IjokaClient] = None


def get_client() -> IjokaClient:
    """Get the global client instance."""
    if _client is None:
        raise HTTPException(status_code=503, detail="Database not connected")
    return _client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - connect/disconnect from database."""
    global _client
    _client = IjokaClient()
    _client.ensure_project()
    yield
    if _client:
        _client.close()
        _client = None


app = FastAPI(
    title="Ijoka API",
    description="HTTP API for AI agent observability and orchestration",
    version="0.1.0",
    lifespan=lifespan,
)


# =============================================================================
# STATUS ENDPOINTS
# =============================================================================


@app.get("/", response_model=MessageResponse, tags=["Status"])
async def root():
    """API root - health check."""
    return MessageResponse(message="Ijoka API is running")


@app.get("/status", response_model=StatusResponse, tags=["Status"])
async def get_status():
    """Get current project status."""
    client = get_client()
    project = client.ensure_project()
    stats = client.get_stats()
    current_feature = client.get_active_feature()

    return StatusResponse(
        project=project,
        stats=stats,
        current_feature=current_feature,
    )


# =============================================================================
# FEATURE ENDPOINTS
# =============================================================================


@app.get("/features", response_model=FeatureListResponse, tags=["Features"])
async def list_features(
    status: Optional[FeatureStatus] = Query(default=None, description="Filter by status"),
    category: Optional[FeatureCategory] = Query(default=None, description="Filter by category"),
):
    """List all features with optional filtering."""
    client = get_client()
    status_str = status.value if status else None
    category_str = category.value if category else None

    features = client.list_features(status=status_str, category=category_str)
    stats = client.get_stats()

    return FeatureListResponse(
        features=features,
        count=len(features),
        stats=stats,
    )


@app.get("/features/{feature_id}", response_model=FeatureResponse, tags=["Features"])
async def get_feature(feature_id: str):
    """Get a specific feature by ID."""
    client = get_client()
    feature = client.get_feature(feature_id)

    if not feature:
        raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")

    return FeatureResponse(feature=feature)


@app.post("/features", response_model=FeatureResponse, tags=["Features"])
async def create_feature(request: CreateFeatureRequest):
    """Create a new feature."""
    client = get_client()

    feature = client.create_feature(
        description=request.description,
        category=request.category.value,
        priority=request.priority,
        steps=request.steps,
        branch_hint=request.branch_hint,
        file_patterns=request.file_patterns,
        work_item_type=request.type.value,
    )

    return FeatureResponse(
        feature=feature,
        message=f"Created {request.type.value}: {feature.description}",
    )


@app.post("/features/{feature_id}/start", response_model=FeatureResponse, tags=["Features"])
async def start_feature(feature_id: str, agent: str = Query(default="api", description="Agent identifier")):
    """Start working on a feature."""
    client = get_client()

    try:
        feature = client.start_feature(feature_id=feature_id, agent=agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FeatureResponse(
        feature=feature,
        message=f"Started feature: {feature.description}",
    )


@app.post("/features/next/start", response_model=FeatureResponse, tags=["Features"])
async def start_next_feature(agent: str = Query(default="api", description="Agent identifier")):
    """Start the next available feature (highest priority pending)."""
    client = get_client()

    try:
        feature = client.start_feature(agent=agent)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FeatureResponse(
        feature=feature,
        message=f"Started feature: {feature.description}",
    )


@app.post("/features/{feature_id}/complete", response_model=FeatureResponse, tags=["Features"])
async def complete_feature(feature_id: str, summary: Optional[str] = Query(default=None)):
    """Mark a feature as complete."""
    client = get_client()

    try:
        feature = client.complete_feature(feature_id=feature_id, summary=summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FeatureResponse(
        feature=feature,
        message=f"Completed feature: {feature.description}",
    )


@app.post("/features/{feature_id}/block", response_model=FeatureResponse, tags=["Features"])
async def block_feature(feature_id: str, request: BlockFeatureRequest):
    """Mark a feature as blocked."""
    client = get_client()

    try:
        feature = client.block_feature(
            feature_id=feature_id,
            reason=request.reason,
            blocking_feature_id=request.blocking_feature_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FeatureResponse(
        feature=feature,
        message=f"Blocked feature: {feature.description}",
    )


@app.patch("/features/{feature_id}", response_model=FeatureResponse, tags=["Features"])
async def update_feature(feature_id: str, request: UpdateFeatureRequest):
    """Update a feature's properties."""
    client = get_client()

    try:
        feature = client.update_feature(
            feature_id=feature_id,
            description=request.description,
            category=request.category.value if request.category else None,
            priority=request.priority,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FeatureResponse(
        feature=feature,
        message=f"Updated feature: {feature.description}",
    )


@app.delete("/features/{feature_id}", response_model=MessageResponse, tags=["Features"])
async def archive_feature(feature_id: str):
    """Archive (delete) a feature."""
    client = get_client()
    success = client.archive_feature(feature_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")

    return MessageResponse(message=f"Archived feature: {feature_id}")


# =============================================================================
# PLAN ENDPOINTS
# =============================================================================


@app.post("/features/{feature_id}/plan", response_model=PlanResponse, tags=["Planning"])
async def set_plan_for_feature(feature_id: str, request: SetPlanRequest):
    """Set implementation plan for a specific feature."""
    client = get_client()

    try:
        # Check if feature exists
        feature = client.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")

        # Set plan (method to be implemented in db.py)
        if not hasattr(client, 'set_plan'):
            raise HTTPException(
                status_code=501,
                detail="set_plan not yet implemented in database client"
            )

        steps = client.set_plan(feature_id=feature_id, steps=request.steps)

        # Calculate progress
        total = len(steps)
        completed = sum(1 for s in steps if s.get('status') == 'completed')
        progress = {
            'total': total,
            'completed': completed,
            'remaining': total - completed,
            'percentage': int((completed / total * 100)) if total > 0 else 0,
        }

        # Find active step
        active_step = next((s for s in steps if s.get('status') == 'in_progress'), None)

        return PlanResponse(
            feature_id=feature_id,
            steps=steps,
            active_step=active_step,
            progress=progress,
            message=f"Set plan with {total} steps for feature: {feature.description}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/features/{feature_id}/plan", response_model=PlanResponse, tags=["Planning"])
async def get_plan_for_feature(feature_id: str):
    """Get implementation plan for a specific feature."""
    client = get_client()

    try:
        # Check if feature exists
        feature = client.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")

        # Get plan (method to be implemented in db.py)
        if not hasattr(client, 'get_plan'):
            raise HTTPException(
                status_code=501,
                detail="get_plan not yet implemented in database client"
            )

        plan_data = client.get_plan(feature_id=feature_id)

        # get_plan returns dict with steps, active_step, progress
        return PlanResponse(
            feature_id=feature_id,
            steps=[s.model_dump() for s in plan_data["steps"]],
            active_step=plan_data["active_step"].model_dump() if plan_data["active_step"] else None,
            progress=plan_data["progress"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/plan", response_model=PlanResponse, tags=["Planning"])
async def set_plan_for_active(request: SetPlanRequest):
    """Set implementation plan for the active feature."""
    client = get_client()

    try:
        # Get active feature
        feature = client.get_active_feature()
        if not feature:
            raise HTTPException(status_code=404, detail="No active feature")

        # Set plan (method to be implemented in db.py)
        if not hasattr(client, 'set_plan'):
            raise HTTPException(
                status_code=501,
                detail="set_plan not yet implemented in database client"
            )

        steps = client.set_plan(feature_id=feature.id, steps=request.steps)

        # Calculate progress
        total = len(steps)
        completed = sum(1 for s in steps if s.get('status') == 'completed')
        progress = {
            'total': total,
            'completed': completed,
            'remaining': total - completed,
            'percentage': int((completed / total * 100)) if total > 0 else 0,
        }

        # Find active step
        active_step = next((s for s in steps if s.get('status') == 'in_progress'), None)

        return PlanResponse(
            feature_id=feature.id,
            steps=steps,
            active_step=active_step,
            progress=progress,
            message=f"Set plan with {total} steps for active feature: {feature.description}",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/plan", response_model=PlanResponse, tags=["Planning"])
async def get_plan_for_active():
    """Get implementation plan for the active feature."""
    client = get_client()

    try:
        # Get active feature
        feature = client.get_active_feature()
        if not feature:
            raise HTTPException(status_code=404, detail="No active feature")

        # Get plan (method to be implemented in db.py)
        if not hasattr(client, 'get_plan'):
            raise HTTPException(
                status_code=501,
                detail="get_plan not yet implemented in database client"
            )

        plan_data = client.get_plan(feature_id=feature.id)

        # get_plan returns dict with steps, active_step, progress
        return PlanResponse(
            feature_id=feature.id,
            steps=[s.model_dump() for s in plan_data["steps"]],
            active_step=plan_data["active_step"].model_dump() if plan_data["active_step"] else None,
            progress=plan_data["progress"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# CHECKPOINT ENDPOINT
# =============================================================================


@app.post("/checkpoint", response_model=CheckpointResponse, tags=["Planning"])
async def report_checkpoint(request: CheckpointRequest):
    """Report progress checkpoint for the active feature."""
    client = get_client()

    try:
        # Get active feature
        feature = client.get_active_feature()
        if not feature:
            raise HTTPException(status_code=404, detail="No active feature")

        # Record checkpoint (method to be implemented in db.py)
        if not hasattr(client, 'checkpoint'):
            raise HTTPException(
                status_code=501,
                detail="checkpoint not yet implemented in database client"
            )

        result = client.checkpoint(
            feature_id=feature.id,
            step_completed=request.step_completed,
            current_activity=request.current_activity,
        )

        # Extract data from result
        steps = result.get('steps', [])
        active_step = result.get('active_step')
        warnings = result.get('warnings', [])

        # Calculate progress
        total = len(steps)
        completed = sum(1 for s in steps if s.get('status') == 'completed')
        progress = {
            'total': total,
            'completed': completed,
            'remaining': total - completed,
            'percentage': int((completed / total * 100)) if total > 0 else 0,
        }

        return CheckpointResponse(
            feature={'id': feature.id, 'description': feature.description},
            active_step=active_step,
            progress=progress,
            warnings=warnings,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# DISCOVER FEATURE ENDPOINT
# =============================================================================


@app.post("/features/discover", response_model=FeatureResponse, tags=["Features"])
async def discover_feature(request: DiscoverFeatureRequest):
    """Discover and create feature from recent activity."""
    client = get_client()

    try:
        # Discover feature (method to be implemented in db.py)
        if not hasattr(client, 'discover_feature'):
            raise HTTPException(
                status_code=501,
                detail="discover_feature not yet implemented in database client"
            )

        result = client.discover_feature(
            description=request.description,
            category=request.category.value,
            priority=request.priority,
            steps=request.steps,
            lookback_minutes=request.lookback_minutes,
            mark_complete=request.mark_complete,
            work_item_type=request.type.value,
        )
        feature = result["feature"]

        message = f"Discovered and created feature: {feature.description}"
        if request.mark_complete:
            message = f"Discovered and completed feature: {feature.description}"

        return FeatureResponse(
            feature=feature,
            message=message,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# INSIGHT ENDPOINTS
# =============================================================================


@app.get("/insights", response_model=InsightListResponse, tags=["Insights"])
async def list_insights(
    query: Optional[str] = Query(default=None, description="Search query"),
    tags: Optional[str] = Query(default=None, description="Comma-separated tags"),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
):
    """List insights with optional filtering."""
    client = get_client()
    tag_list = [t.strip() for t in tags.split(",")] if tags else None

    insights = client.list_insights(query=query, tags=tag_list, limit=limit)

    return InsightListResponse(
        insights=insights,
        count=len(insights),
    )


@app.post("/insights", response_model=InsightResponse, tags=["Insights"])
async def record_insight(request: RecordInsightRequest):
    """Record a new insight."""
    client = get_client()

    insight = client.record_insight(
        description=request.description,
        pattern_type=request.pattern_type.value,
        tags=request.tags,
        feature_id=request.feature_id,
    )

    return InsightResponse(
        insight=insight,
        message=f"Recorded insight: {insight.description[:50]}...",
    )


# =============================================================================
# ANALYTICS ENDPOINTS
# =============================================================================


@app.get("/analytics/patterns", response_model=PatternAnalysisResponse, tags=["Analytics"])
async def get_patterns():
    """Get discovered patterns and feature clusters."""
    client = get_client()
    detector = PatternDetector(client)

    return PatternAnalysisResponse(
        clusters=detector.detect_feature_clusters(),
        patterns=detector.find_common_workflows(min_frequency=1),
        bottlenecks=detector.detect_bottlenecks()
    )


@app.get("/analytics/velocity", response_model=VelocityResponse, tags=["Analytics"])
async def get_velocity(days: int = Query(7, ge=1, le=365, description="Time window in days")):
    """Get productivity velocity metrics."""
    client = get_client()
    analyzer = TemporalAnalyzer(client)

    current = analyzer.compute_velocity(window_days=days)
    drift_warnings = analyzer.detect_velocity_drift()

    return VelocityResponse(
        current=current,
        drift_warnings=drift_warnings
    )


@app.get("/analytics/profile/{agent}", response_model=AgentProfileResponse, tags=["Analytics"])
async def get_agent_profile(agent: str = Path(..., description="Agent identifier")):
    """Get behavioral profile for an agent."""
    client = get_client()
    profiler = AgentProfiler(client)

    profile = profiler.build_profile(agent)

    return AgentProfileResponse(profile=profile)


@app.get("/analytics/agents", tags=["Analytics"])
async def list_agents():
    """List all agents that have worked on features."""
    client = get_client()
    profiler = AgentProfiler(client)

    return {"agents": profiler.list_agents()}


@app.post("/analytics/query", response_model=AnalyticsQueryResponse, tags=["Analytics"])
async def query_analytics(request: AnalyticsQueryRequest):
    """Execute a natural language analytics query."""
    client = get_client()
    engine = AgenticQueryEngine(client)

    return engine.query(request.question)


@app.get("/analytics/digest", response_model=DailyDigestResponse, tags=["Analytics"])
async def get_daily_digest():
    """Get daily digest of top insights."""
    from datetime import datetime

    client = get_client()
    synthesizer = InsightSynthesizer(client)
    detector = PatternDetector(client)
    analyzer = TemporalAnalyzer(client)

    return DailyDigestResponse(
        date=datetime.now(),
        top_insights=synthesizer.generate_daily_digest(max_insights=10),
        velocity=analyzer.compute_velocity(),
        active_bottlenecks=detector.detect_bottlenecks()
    )


@app.get("/analytics/summary", tags=["Analytics"])
async def get_analytics_summary():
    """Get comprehensive analytics summary."""
    client = get_client()
    synthesizer = InsightSynthesizer(client)

    return synthesizer.get_summary()


# Self-Improvement Loop Endpoints

class InsightFeedbackRequest(BaseModel):
    """Request for insight feedback."""
    insight_id: str = Field(..., description="Insight identifier")
    helpful: bool = Field(..., description="Whether the insight was helpful")
    comment: Optional[str] = Field(None, description="Optional feedback comment")


@app.post("/analytics/feedback", tags=["Analytics"])
async def submit_insight_feedback(request: InsightFeedbackRequest):
    """Submit feedback for an insight to improve future recommendations."""
    from .analytics import SelfImprovementLoop

    client = get_client()
    loop = SelfImprovementLoop(client)

    success = loop.record_feedback(request.insight_id, request.helpful, request.comment)

    return {
        "success": success,
        "insight_id": request.insight_id,
        "helpful": request.helpful,
    }


@app.get("/analytics/effectiveness", tags=["Analytics"])
async def get_insight_effectiveness():
    """Get insight effectiveness metrics based on user feedback."""
    from .analytics import SelfImprovementLoop

    client = get_client()
    loop = SelfImprovementLoop(client)

    return loop.get_feedback_summary()


# =============================================================================
# TRANSCRIPT ENDPOINTS
# =============================================================================


class TranscriptSyncRequest(BaseModel):
    """Request to sync transcripts."""
    session_id: Optional[str] = Field(default=None, description="Specific session to sync")
    limit: int = Field(default=50, ge=1, le=500, description="Max sessions to sync")
    clear_existing: bool = Field(default=False, description="Clear existing data before sync")


class TranscriptStatsResponse(BaseModel):
    """Response for transcript statistics."""
    success: bool = True
    session_count: int
    total_entries: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_creation_tokens: int
    total_cache_read_tokens: int
    days: int


class ToolUsageResponse(BaseModel):
    """Response for tool usage breakdown."""
    success: bool = True
    days: int
    tools: list[dict]


class ModelUsageResponse(BaseModel):
    """Response for model usage breakdown."""
    success: bool = True
    days: int
    models: list[dict]


class TranscriptEntriesResponse(BaseModel):
    """Response for transcript entries."""
    success: bool = True
    session_id: str
    entries: list[dict]
    count: int


class TranscriptSyncResponse(BaseModel):
    """Response for transcript sync."""
    success: bool = True
    total_sessions: int
    synced: int
    failed: int
    total_entries: int
    total_tool_uses: int
    errors: list[str] = Field(default_factory=list)


def _get_graph_helper():
    """Import and return graph_db_helper module."""
    import sys
    from pathlib import Path

    # Add path to graph_db_helper
    scripts_path = Path(__file__).parent.parent.parent.parent / "claude-plugin" / "hooks" / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    try:
        import graph_db_helper
        return graph_db_helper
    except ImportError:
        raise HTTPException(status_code=503, detail="graph_db_helper not available")


@app.get("/transcripts/stats", response_model=TranscriptStatsResponse, tags=["Transcripts"])
async def get_transcript_stats(
    days: int = Query(default=7, ge=1, le=365, description="Days to look back"),
    project_path: Optional[str] = Query(default=None, description="Project path"),
):
    """Get aggregate transcript statistics from Memgraph."""
    import os

    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    project = project_path or os.getcwd()
    stats = db.get_transcript_stats(project, days=days)

    return TranscriptStatsResponse(**stats)


@app.get("/transcripts/tools", response_model=ToolUsageResponse, tags=["Transcripts"])
async def get_tool_usage(
    days: int = Query(default=7, ge=1, le=365, description="Days to look back"),
    project_path: Optional[str] = Query(default=None, description="Project path"),
    limit: int = Query(default=20, ge=1, le=100, description="Max tools to return"),
):
    """Get tool usage breakdown from transcripts."""
    import os

    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    project = project_path or os.getcwd()
    tools = db.get_tool_usage_breakdown(project, days=days)[:limit]

    return ToolUsageResponse(days=days, tools=tools)


@app.get("/transcripts/models", response_model=ModelUsageResponse, tags=["Transcripts"])
async def get_model_usage(
    days: int = Query(default=7, ge=1, le=365, description="Days to look back"),
    project_path: Optional[str] = Query(default=None, description="Project path"),
):
    """Get model usage breakdown from transcripts."""
    import os

    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    project = project_path or os.getcwd()
    models = db.get_model_usage_breakdown(project, days=days)

    return ModelUsageResponse(days=days, models=models)


@app.get("/transcripts/sessions/{session_id}/entries", response_model=TranscriptEntriesResponse, tags=["Transcripts"])
async def get_transcript_entries(
    session_id: str = Path(..., description="Session ID"),
    entry_type: Optional[str] = Query(default=None, description="Filter by type (user/assistant)"),
    limit: int = Query(default=100, ge=1, le=500, description="Max entries to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
):
    """Get transcript entries for a specific session."""
    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    entries = db.get_transcript_entries(session_id, entry_type=entry_type, limit=limit, offset=offset)

    return TranscriptEntriesResponse(
        session_id=session_id,
        entries=entries,
        count=len(entries),
    )


@app.get("/transcripts/sessions/{session_id}", tags=["Transcripts"])
async def get_transcript_session(session_id: str = Path(..., description="Session ID")):
    """Get transcript session details."""
    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    session = db.get_transcript_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Transcript session not found: {session_id}")

    return {"success": True, "session": session}


@app.post("/transcripts/sync", response_model=TranscriptSyncResponse, tags=["Transcripts"])
async def sync_transcripts(request: TranscriptSyncRequest):
    """Sync transcript data to Memgraph."""
    import os
    from .transcript import (
        TranscriptParser,
        sync_transcript_to_graph,
        sync_all_transcripts_to_graph
    )

    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    project_path = os.getcwd()

    if request.session_id:
        # Sync single session
        parser = TranscriptParser(project_path)
        result = sync_transcript_to_graph(
            parser=parser,
            session_id=request.session_id,
            clear_existing=request.clear_existing
        )

        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])

        return TranscriptSyncResponse(
            total_sessions=1,
            synced=1 if result.get("success") else 0,
            failed=0 if result.get("success") else 1,
            total_entries=result.get("entries_synced", 0),
            total_tool_uses=result.get("tool_uses_synced", 0),
            errors=result.get("errors", []),
        )
    else:
        # Sync all sessions
        result = sync_all_transcripts_to_graph(
            project_path=project_path,
            limit=request.limit,
            clear_existing=request.clear_existing
        )

        return TranscriptSyncResponse(**result)


@app.get("/transcripts/sessions/{session_id}/tools", tags=["Transcripts"])
async def get_session_tool_uses(
    session_id: str = Path(..., description="Session ID"),
    tool_name: Optional[str] = Query(default=None, description="Filter by tool name"),
):
    """Get tool uses from a specific transcript session."""
    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    tools = db.get_transcript_tool_uses(session_id, tool_name=tool_name)

    return {"success": True, "session_id": session_id, "tool_uses": tools, "count": len(tools)}


class SummarizeRequest(BaseModel):
    """Request to generate a session summary."""
    model: str = Field(default="haiku", description="Claude model to use")


class SessionSummaryResponse(BaseModel):
    """Response for session summary."""
    success: bool = True
    session_id: str
    title: str
    summary: str
    key_actions: list[str]
    tools_highlighted: list[str]
    files_modified: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    model: str


@app.post("/transcripts/sessions/{session_id}/summarize", response_model=SessionSummaryResponse, tags=["Transcripts"])
async def summarize_session(
    session_id: str = Path(..., description="Session ID to summarize"),
    request: Optional[SummarizeRequest] = None,
):
    """
    Generate a summary for a transcript session using Claude CLI headless mode.

    Uses the same authentication as the user's Claude Code installation.
    Default model is Haiku for cost efficiency.
    """
    from .summarizer import generate_session_summary, check_claude_cli_available

    if not check_claude_cli_available():
        raise HTTPException(
            status_code=503,
            detail="Claude CLI not found. Is Claude Code installed?"
        )

    db = _get_graph_helper()
    if not db.is_connected():
        raise HTTPException(status_code=503, detail="Memgraph not connected")

    model = request.model if request else "haiku"

    try:
        summary = generate_session_summary(session_id, model=model)

        if "Failed" in summary.title or "Error" in summary.summary:
            raise HTTPException(status_code=500, detail=summary.summary)

        return SessionSummaryResponse(
            session_id=session_id,
            title=summary.title,
            summary=summary.summary,
            key_actions=summary.key_actions,
            tools_highlighted=summary.tools_highlighted,
            files_modified=summary.files_modified,
            decisions_made=summary.decisions_made,
            model=summary.model,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
):
    """
    Run the FastAPI server.

    Args:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8000)
        reload: Enable auto-reload for development
    """
    import uvicorn

    print(f"Starting Ijoka API server on http://{host}:{port}")
    print(f"Swagger UI: http://{host}:{port}/docs")
    print(f"OpenAPI spec: http://{host}:{port}/openapi.json")

    uvicorn.run("ijoka.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
