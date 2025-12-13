"""
Ijoka - CLI and SDK for AI agent observability and orchestration.

Usage:
    # As CLI
    $ ijoka status
    $ ijoka feature list

    # As SDK
    from ijoka import IjokaClient
    client = IjokaClient()
    features = client.list_features()
"""

from .db import IjokaClient, get_client
from .models import (
    Feature,
    FeatureCategory,
    FeatureListItem,
    FeatureStatus,
    Insight,
    InsightType,
    Project,
    ProjectStats,
    Session,
    SessionStatus,
    Step,
    StepStatus,
)

__version__ = "0.1.0"
__all__ = [
    # Client
    "IjokaClient",
    "get_client",
    # Models
    "Feature",
    "FeatureCategory",
    "FeatureListItem",
    "FeatureStatus",
    "Insight",
    "InsightType",
    "Project",
    "ProjectStats",
    "Session",
    "SessionStatus",
    "Step",
    "StepStatus",
]
