"""
Ijoka Query Engine - Natural language interface to analytics.

Classifies user queries and routes them to appropriate analytics modules.
"""

import re
from typing import Optional

from loguru import logger

from .analytics import InsightSynthesizer, PatternDetector, TemporalAnalyzer, AgentProfiler
from .models import AnalyticsQueryResponse, AnalyticsInsight


class AgenticQueryEngine:
    """Natural language to analytics query engine."""

    # Query classification patterns
    VELOCITY_PATTERNS = [
        r"\b(velocity|speed|productivity|fast|slow|throughput|rate)\b",
        r"\b(how many|count).*(complete|finish|done)\b",
        r"\b(features?\s+per\s+(day|week))\b",
    ]

    BOTTLENECK_PATTERNS = [
        r"\b(block|stuck|bottleneck|problem|issue|delay)\b",
        r"\b(why.*(slow|stuck|blocked))\b",
        r"\b(what.*blocking)\b",
    ]

    PROFILE_PATTERNS = [
        r"\b(profile|agent|who|performance|team)\b",
        r"\b(best|top).*(agent|developer)\b",
        r"\b(my|agent).*(stats|statistics|performance)\b",
    ]

    PATTERN_PATTERNS = [
        r"\b(pattern|workflow|sequence|common|typical)\b",
        r"\b(how.*(usually|typically|normally))\b",
        r"\b(cluster|group|category)\b",
    ]

    def __init__(self, client):
        """Initialize with IjokaClient instance."""
        self.client = client
        self.synthesizer = InsightSynthesizer(client)
        self.pattern_detector = PatternDetector(client)
        self.temporal_analyzer = TemporalAnalyzer(client)
        self.agent_profiler = AgentProfiler(client)

    def query(self, natural_language: str) -> AnalyticsQueryResponse:
        """Execute a natural language query and return structured results."""
        query_lower = natural_language.lower().strip()

        # Classify the query
        query_type = self._classify_query(query_lower)
        logger.info(f"Query classified as: {query_type}")

        try:
            if query_type == "velocity":
                return self._handle_velocity_query(query_lower)
            elif query_type == "bottlenecks":
                return self._handle_bottleneck_query(query_lower)
            elif query_type == "profile":
                return self._handle_profile_query(query_lower)
            elif query_type == "patterns":
                return self._handle_pattern_query(query_lower)
            else:
                return self._handle_general_query(query_lower)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return AnalyticsQueryResponse(
                success=False,
                query_type="error",
                data={"error": str(e), "original_query": natural_language}
            )

    def _classify_query(self, text: str) -> str:
        """Classify query intent based on patterns."""
        # Check each category
        for pattern in self.VELOCITY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "velocity"

        for pattern in self.BOTTLENECK_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "bottlenecks"

        for pattern in self.PROFILE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "profile"

        for pattern in self.PATTERN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return "patterns"

        return "general"

    def _handle_velocity_query(self, query: str) -> AnalyticsQueryResponse:
        """Handle velocity-related queries."""
        # Extract time window if specified
        window_days = 7
        if "month" in query:
            window_days = 30
        elif "two weeks" in query or "2 weeks" in query:
            window_days = 14
        elif "today" in query:
            window_days = 1

        velocity = self.temporal_analyzer.compute_velocity(window_days=window_days)
        drift_warnings = self.temporal_analyzer.detect_velocity_drift()

        insights = []
        if drift_warnings:
            for warning in drift_warnings:
                insights.append(AnalyticsInsight(
                    id="velocity-drift",
                    insight_type="anomaly",
                    description=warning,
                    impact_score=0.7,
                    confidence=0.8
                ))

        return AnalyticsQueryResponse(
            success=True,
            query_type="velocity",
            data={
                "metrics": velocity.model_dump(),
                "window_days": window_days,
                "drift_warnings": drift_warnings,
            },
            insights=insights
        )

    def _handle_bottleneck_query(self, query: str) -> AnalyticsQueryResponse:
        """Handle bottleneck-related queries."""
        bottlenecks = self.pattern_detector.detect_bottlenecks()

        insights = []
        for b in bottlenecks[:5]:
            insights.append(AnalyticsInsight(
                id=b.id,
                insight_type="bottleneck",
                description=f"{b.description}: {b.block_reason}" if b.block_reason else b.description or "Unknown",
                impact_score=0.8 if b.severity.value in ("critical", "high") else 0.5,
                confidence=0.9,
                related_features=[b.feature_id]
            ))

        return AnalyticsQueryResponse(
            success=True,
            query_type="bottlenecks",
            data={
                "count": len(bottlenecks),
                "bottlenecks": [b.model_dump() for b in bottlenecks],
            },
            insights=insights
        )

    def _handle_profile_query(self, query: str) -> AnalyticsQueryResponse:
        """Handle agent profile queries."""
        # Try to extract agent name from query
        agent_id = self._extract_agent(query)

        if agent_id:
            profile = self.agent_profiler.build_profile(agent_id)
            return AnalyticsQueryResponse(
                success=True,
                query_type="profile",
                data={"profile": profile.model_dump()},
            )
        else:
            # List all agents
            agents = self.agent_profiler.list_agents()
            profiles = [self.agent_profiler.build_profile(a).model_dump() for a in agents[:5]]

            return AnalyticsQueryResponse(
                success=True,
                query_type="profile",
                data={
                    "agents": agents,
                    "profiles": profiles,
                },
            )

    def _handle_pattern_query(self, query: str) -> AnalyticsQueryResponse:
        """Handle pattern/workflow queries."""
        clusters = self.pattern_detector.detect_feature_clusters()
        workflows = self.pattern_detector.find_common_workflows(min_frequency=1)

        return AnalyticsQueryResponse(
            success=True,
            query_type="patterns",
            data={
                "clusters": [c.model_dump() for c in clusters],
                "workflows": [w.model_dump() for w in workflows[:10]],
            },
        )

    def _handle_general_query(self, query: str) -> AnalyticsQueryResponse:
        """Handle general queries with daily digest."""
        insights = self.synthesizer.generate_daily_digest(max_insights=10)
        summary = self.synthesizer.get_summary()

        return AnalyticsQueryResponse(
            success=True,
            query_type="general",
            data=summary,
            insights=insights
        )

    def _extract_agent(self, query: str) -> Optional[str]:
        """Try to extract agent name from query."""
        # Common agent names
        known_agents = ["claude-code", "claude", "codex", "gemini", "cursor"]

        for agent in known_agents:
            if agent in query.lower():
                return agent

        # Check for "my" which implies current user/agent
        if " my " in f" {query} " or query.startswith("my "):
            return "claude-code"  # Default agent

        return None

    def suggest_queries(self) -> list[str]:
        """Return example queries users can ask."""
        return [
            "What is my velocity this week?",
            "What's blocking progress?",
            "Show me agent performance",
            "What are the common workflow patterns?",
            "How many features did we complete?",
            "Why is development slow?",
            "Who is the best agent for infrastructure tasks?",
            "Give me a daily digest",
        ]
