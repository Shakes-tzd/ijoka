"""
Ijoka Analytics Module - Pattern Detection, Temporal Analysis, and Agent Profiling.
"""

from datetime import datetime, timedelta
from typing import Optional
import uuid

import pandas as pd
from loguru import logger

from .models import (
    FeatureCluster, WorkflowPattern, Bottleneck, BottleneckSeverity,
    FeatureCategory, VelocityMetrics, VelocityTrend, AgentProfile,
    AnalyticsInsight, AnalyticsInsightType,
)


class PatternDetector:
    """Detect patterns in feature and workflow data using graph analysis."""

    def __init__(self, client):
        """Initialize with IjokaClient instance."""
        self.client = client

    def detect_feature_clusters(self) -> list[FeatureCluster]:
        """Group features by category and completion patterns."""
        with self.client.session() as session:
            # First get clusters by category
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WITH f.category as category, collect(f) as features
                WHERE size(features) > 1
                RETURN category,
                       [feat IN features | feat.id] as feature_ids,
                       size(features) as count
                ORDER BY count DESC
            """, path=self.client._project_path)

            clusters = []
            for record in result:
                category = record["category"]
                feature_ids = record["feature_ids"]
                count = record["count"]

                clusters.append(FeatureCluster(
                    id=str(uuid.uuid4()),
                    name=f"{category} features",
                    feature_ids=feature_ids,
                    common_category=FeatureCategory(category) if category else None,
                    avg_completion_time=None,  # Calculated separately if needed
                    size=count
                ))

            return clusters

    def find_common_workflows(self, min_frequency: int = 2) -> list[WorkflowPattern]:
        """Find recurring step sequences across features."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (s:Step)-[:BELONGS_TO]->(f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.status = 'complete'
                WITH f, s ORDER BY s.step_order
                WITH f, collect(s.description) as steps
                WHERE size(steps) > 0
                WITH steps, count(*) as freq
                WHERE freq >= $min_freq
                RETURN steps, freq
                ORDER BY freq DESC
                LIMIT 20
            """, path=self.client._project_path, min_freq=min_frequency)

            patterns = []
            for record in result:
                steps = record["steps"]
                freq = record["freq"]

                patterns.append(WorkflowPattern(
                    id=str(uuid.uuid4()),
                    sequence=steps,
                    frequency=freq,
                    success_rate=1.0  # Only completed features included
                ))

            return patterns

    def detect_bottlenecks(self) -> list[Bottleneck]:
        """Find features or steps that frequently block progress."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.status = 'blocked' OR f.block_reason IS NOT NULL
                RETURN f.id as feature_id,
                       f.description as description,
                       f.block_reason as reason,
                       f.updated_at as updated_at
                ORDER BY f.updated_at DESC
            """, path=self.client._project_path)

            bottlenecks = []
            now = datetime.now()

            for record in result:
                feature_id = record["feature_id"]
                description = record["description"]
                reason = record["reason"]
                updated_at = record.get("updated_at")

                # Calculate hours blocked
                hours_blocked = None
                if updated_at:
                    try:
                        if hasattr(updated_at, 'to_native'):
                            updated_dt = updated_at.to_native()
                        else:
                            updated_dt = updated_at
                        hours_blocked = (now - updated_dt.replace(tzinfo=None)).total_seconds() / 3600
                    except Exception:
                        pass

                # Determine severity based on block duration
                if hours_blocked is not None:
                    if hours_blocked > 72:
                        severity = BottleneckSeverity.CRITICAL
                    elif hours_blocked > 24:
                        severity = BottleneckSeverity.HIGH
                    elif hours_blocked > 8:
                        severity = BottleneckSeverity.MEDIUM
                    else:
                        severity = BottleneckSeverity.LOW
                else:
                    severity = BottleneckSeverity.MEDIUM

                bottlenecks.append(Bottleneck(
                    id=str(uuid.uuid4()),
                    feature_id=feature_id,
                    description=description,
                    severity=severity,
                    avg_block_duration=hours_blocked,
                    block_reason=reason
                ))

            return bottlenecks


class TemporalAnalyzer:
    """Time-series analysis for velocity and productivity patterns."""

    def __init__(self, client):
        """Initialize with IjokaClient instance."""
        self.client = client

    def compute_velocity(self, window_days: int = 7) -> VelocityMetrics:
        """Calculate feature completion velocity for a time window."""
        now = datetime.now()
        period_start = now - timedelta(days=window_days)

        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.created_at IS NOT NULL
                RETURN f.status as status,
                       f.created_at as created_at,
                       f.completed_at as completed_at
            """, path=self.client._project_path)

            records = list(result)

            if not records:
                return VelocityMetrics(
                    period_start=period_start,
                    period_end=now,
                    features_completed=0,
                    features_started=0,
                    trend=VelocityTrend.STABLE
                )

            # Convert to pandas DataFrame
            data = []
            for r in records:
                created = r.get("created_at")
                completed = r.get("completed_at")

                # Convert neo4j datetime to python datetime
                if created and hasattr(created, 'to_native'):
                    created = created.to_native().replace(tzinfo=None)
                if completed and hasattr(completed, 'to_native'):
                    completed = completed.to_native().replace(tzinfo=None)

                data.append({
                    "status": r["status"],
                    "created_at": created,
                    "completed_at": completed
                })

            df = pd.DataFrame(data)

            # Filter to window
            features_started = 0
            features_completed = 0
            cycle_times = []

            for _, row in df.iterrows():
                created = row["created_at"]
                completed = row["completed_at"]

                if created and created >= period_start:
                    features_started += 1

                if completed and completed >= period_start:
                    features_completed += 1
                    if created:
                        cycle_time = (completed - created).total_seconds() / 3600
                        cycle_times.append(cycle_time)

            avg_cycle_time = sum(cycle_times) / len(cycle_times) if cycle_times else None
            features_per_day = features_completed / window_days if window_days > 0 else 0

            return VelocityMetrics(
                period_start=period_start,
                period_end=now,
                features_completed=features_completed,
                features_started=features_started,
                avg_cycle_time=avg_cycle_time,
                trend=VelocityTrend.STABLE,
                features_per_day=features_per_day
            )

    def detect_velocity_drift(self, threshold: float = 0.3) -> list[str]:
        """Detect significant velocity changes between periods."""
        current = self.compute_velocity(window_days=7)
        previous = self.compute_velocity(window_days=14)

        warnings = []

        # Compare completion rates
        if previous.features_completed > 0:
            # Normalize previous to 7-day equivalent
            prev_normalized = previous.features_completed / 2
            if prev_normalized > 0:
                change = (current.features_completed - prev_normalized) / prev_normalized
                if change < -threshold:
                    warnings.append(f"Velocity decreased by {abs(change):.0%} compared to previous period")
                elif change > threshold:
                    warnings.append(f"Velocity improved by {change:.0%} compared to previous period")

        # Check for stalled work
        if current.features_started > 0 and current.features_completed == 0:
            warnings.append("Features started but none completed in the past week")

        return warnings

    def get_productivity_by_hour(self) -> dict[int, int]:
        """Analyze which hours of day have most completions."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.completed_at IS NOT NULL
                RETURN f.completed_at as completed_at
            """, path=self.client._project_path)

            hour_counts = {h: 0 for h in range(24)}

            for record in result:
                completed = record.get("completed_at")
                if completed:
                    if hasattr(completed, 'to_native'):
                        completed = completed.to_native()
                    hour_counts[completed.hour] += 1

            return hour_counts


class AgentProfiler:
    """Build behavioral profiles for AI agents based on their work patterns."""

    def __init__(self, client):
        """Initialize with IjokaClient instance."""
        self.client = client

    def build_profile(self, agent_id: str) -> AgentProfile:
        """Build comprehensive profile for an agent."""
        with self.client.session() as session:
            # Get features assigned to agent (without duration calculation in Cypher)
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.assigned_agent = $agent OR f.claiming_agent = $agent
                RETURN f.status as status,
                       f.category as category,
                       f.created_at as created_at,
                       f.completed_at as completed_at
            """, path=self.client._project_path, agent=agent_id)

            records = list(result)
            if not records:
                return AgentProfile(agent_id=agent_id)

            total = len(records)
            completed = 0
            categories = set()
            completion_times = []

            for r in records:
                if r["status"] == "complete":
                    completed += 1
                if r["category"]:
                    categories.add(r["category"])

                # Calculate completion time in Python
                created = r.get("created_at")
                completed_at = r.get("completed_at")
                if created and completed_at:
                    try:
                        if hasattr(created, 'to_native'):
                            created = created.to_native()
                        if hasattr(completed_at, 'to_native'):
                            completed_at = completed_at.to_native()
                        hours = (completed_at - created).total_seconds() / 3600
                        completion_times.append(hours)
                    except Exception:
                        pass

            avg_hours = sum(completion_times) / len(completion_times) if completion_times else None

            # Convert categories to enum values
            preferred_categories = []
            for cat in list(categories)[:5]:  # Top 5
                try:
                    preferred_categories.append(FeatureCategory(cat))
                except ValueError:
                    pass

            return AgentProfile(
                agent_id=agent_id,
                total_features=total,
                completed_features=completed,
                avg_completion_time=avg_hours,
                preferred_categories=preferred_categories,
                success_rate=completed / total if total > 0 else None
            )

    def list_agents(self) -> list[str]:
        """List all agents that have worked on features."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.assigned_agent IS NOT NULL OR f.claiming_agent IS NOT NULL
                WITH coalesce(f.assigned_agent, f.claiming_agent) as agent
                RETURN DISTINCT agent
                ORDER BY agent
            """, path=self.client._project_path)

            return [record["agent"] for record in result]

    def compare_agents(self, agent_ids: list[str]) -> list[AgentProfile]:
        """Build profiles for multiple agents for comparison."""
        return [self.build_profile(agent_id) for agent_id in agent_ids]

    def recommend_assignment(self, category: FeatureCategory) -> list[tuple[str, float]]:
        """Recommend agents for a feature based on category success."""
        with self.client.session() as session:
            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.category = $category
                  AND f.status = 'complete'
                  AND (f.assigned_agent IS NOT NULL OR f.claiming_agent IS NOT NULL)
                WITH coalesce(f.assigned_agent, f.claiming_agent) as agent, count(*) as completed
                RETURN agent, completed
                ORDER BY completed DESC
                LIMIT 5
            """, path=self.client._project_path, category=category.value)

            recommendations = []
            total_completed = sum(r["completed"] for r in result)

            result = session.run("""
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.category = $category
                  AND f.status = 'complete'
                  AND (f.assigned_agent IS NOT NULL OR f.claiming_agent IS NOT NULL)
                WITH coalesce(f.assigned_agent, f.claiming_agent) as agent, count(*) as completed
                RETURN agent, completed
                ORDER BY completed DESC
                LIMIT 5
            """, path=self.client._project_path, category=category.value)

            for record in result:
                agent = record["agent"]
                completed = record["completed"]
                score = completed / total_completed if total_completed > 0 else 0
                recommendations.append((agent, score))

            return recommendations


class InsightSynthesizer:
    """Cross-reference findings from all analytics modules to generate actionable insights."""

    def __init__(self, client):
        """Initialize with IjokaClient instance."""
        self.client = client
        self.pattern_detector = PatternDetector(client)
        self.temporal_analyzer = TemporalAnalyzer(client)
        self.agent_profiler = AgentProfiler(client)

    def generate_daily_digest(self, max_insights: int = 10) -> list[AnalyticsInsight]:
        """Generate top insights from all analytics modules."""
        insights = []

        # From bottlenecks
        try:
            bottlenecks = self.pattern_detector.detect_bottlenecks()
            for b in bottlenecks[:3]:
                severity_score = {
                    BottleneckSeverity.CRITICAL: 0.95,
                    BottleneckSeverity.HIGH: 0.8,
                    BottleneckSeverity.MEDIUM: 0.6,
                    BottleneckSeverity.LOW: 0.4,
                }.get(b.severity, 0.5)

                desc = f"Feature blocked: {b.description[:50]}..." if b.description else f"Feature {b.feature_id[:8]} is blocked"
                if b.block_reason:
                    desc += f" Reason: {b.block_reason}"

                insights.append(AnalyticsInsight(
                    id=str(uuid.uuid4()),
                    insight_type=AnalyticsInsightType.BOTTLENECK,
                    description=desc,
                    impact_score=severity_score,
                    confidence=0.9,
                    related_features=[b.feature_id],
                    actionable=True,
                    created_at=datetime.now()
                ))
        except Exception as e:
            logger.warning(f"Failed to analyze bottlenecks: {e}")

        # From velocity drift
        try:
            drift_warnings = self.temporal_analyzer.detect_velocity_drift()
            for warning in drift_warnings:
                insights.append(AnalyticsInsight(
                    id=str(uuid.uuid4()),
                    insight_type=AnalyticsInsightType.ANOMALY,
                    description=warning,
                    impact_score=0.7,
                    confidence=0.75,
                    actionable=True,
                    created_at=datetime.now()
                ))
        except Exception as e:
            logger.warning(f"Failed to detect velocity drift: {e}")

        # From patterns - identify successful workflows
        try:
            patterns = self.pattern_detector.find_common_workflows(min_frequency=2)
            if patterns:
                top_pattern = patterns[0]
                steps_summary = " → ".join(top_pattern.sequence[:3])
                if len(top_pattern.sequence) > 3:
                    steps_summary += "..."

                insights.append(AnalyticsInsight(
                    id=str(uuid.uuid4()),
                    insight_type=AnalyticsInsightType.PATTERN,
                    description=f"Common successful workflow ({top_pattern.frequency}x): {steps_summary}",
                    impact_score=0.5,
                    confidence=0.85,
                    actionable=False,
                    created_at=datetime.now()
                ))
        except Exception as e:
            logger.warning(f"Failed to find workflow patterns: {e}")

        # From velocity - add current metrics as trend insight
        try:
            velocity = self.temporal_analyzer.compute_velocity(window_days=7)
            if velocity.features_completed > 0:
                trend_desc = f"Completed {velocity.features_completed} features in the past week"
                if velocity.avg_cycle_time:
                    trend_desc += f" (avg {velocity.avg_cycle_time:.1f}h cycle time)"

                insights.append(AnalyticsInsight(
                    id=str(uuid.uuid4()),
                    insight_type=AnalyticsInsightType.TREND,
                    description=trend_desc,
                    impact_score=0.4,
                    confidence=0.95,
                    actionable=False,
                    created_at=datetime.now()
                ))
        except Exception as e:
            logger.warning(f"Failed to compute velocity: {e}")

        # Sort by impact * confidence
        insights.sort(key=lambda i: i.impact_score * i.confidence, reverse=True)
        return insights[:max_insights]

    def recommend_actions(self) -> list[AnalyticsInsight]:
        """Generate prioritized actionable recommendations."""
        recommendations = []

        # Check for blocked features
        try:
            bottlenecks = self.pattern_detector.detect_bottlenecks()
            for b in bottlenecks:
                if b.severity in (BottleneckSeverity.CRITICAL, BottleneckSeverity.HIGH):
                    recommendations.append(AnalyticsInsight(
                        id=str(uuid.uuid4()),
                        insight_type=AnalyticsInsightType.RECOMMENDATION,
                        description=f"URGENT: Unblock feature '{b.description[:30]}...' - blocked for {b.avg_block_duration:.0f}h" if b.avg_block_duration else f"URGENT: Unblock feature '{b.description[:30]}...'",
                        impact_score=0.9,
                        confidence=0.95,
                        related_features=[b.feature_id],
                        actionable=True,
                        created_at=datetime.now()
                    ))
        except Exception as e:
            logger.warning(f"Failed to generate bottleneck recommendations: {e}")

        # Check velocity trends
        try:
            drift_warnings = self.temporal_analyzer.detect_velocity_drift(threshold=0.2)
            for warning in drift_warnings:
                if "decreased" in warning.lower():
                    recommendations.append(AnalyticsInsight(
                        id=str(uuid.uuid4()),
                        insight_type=AnalyticsInsightType.RECOMMENDATION,
                        description=f"Review workload: {warning}",
                        impact_score=0.7,
                        confidence=0.8,
                        actionable=True,
                        created_at=datetime.now()
                    ))
        except Exception as e:
            logger.warning(f"Failed to generate velocity recommendations: {e}")

        recommendations.sort(key=lambda i: i.impact_score * i.confidence, reverse=True)
        return recommendations

    def get_summary(self) -> dict:
        """Get a comprehensive analytics summary."""
        summary = {
            "generated_at": datetime.now().isoformat(),
            "clusters": [],
            "bottlenecks": [],
            "velocity": None,
            "top_insights": [],
        }

        try:
            summary["clusters"] = [c.model_dump() for c in self.pattern_detector.detect_feature_clusters()]
        except Exception as e:
            logger.warning(f"Failed to get clusters: {e}")

        try:
            summary["bottlenecks"] = [b.model_dump() for b in self.pattern_detector.detect_bottlenecks()]
        except Exception as e:
            logger.warning(f"Failed to get bottlenecks: {e}")

        try:
            summary["velocity"] = self.temporal_analyzer.compute_velocity().model_dump()
        except Exception as e:
            logger.warning(f"Failed to get velocity: {e}")

        try:
            summary["top_insights"] = [i.model_dump() for i in self.generate_daily_digest(max_insights=5)]
        except Exception as e:
            logger.warning(f"Failed to generate insights: {e}")

        return summary


class SelfImprovementLoop:
    """Track insight effectiveness and refine recommendations based on outcomes."""

    def __init__(self, client):
        """Initialize with IjokaClient instance."""
        self.client = client

    def record_feedback(self, insight_id: str, helpful: bool, comment: Optional[str] = None) -> bool:
        """Record user feedback on an insight.

        Args:
            insight_id: The insight identifier
            helpful: Whether the insight was helpful
            comment: Optional user comment

        Returns:
            True if feedback was recorded successfully
        """
        try:
            with self.client.session(mode="WRITE") as session:
                # Store feedback as a node linked to the insight
                session.run("""
                    MERGE (i:AnalyticsInsight {id: $id})
                    ON CREATE SET i.feedback_count = 1,
                                  i.helpful_count = $helpful,
                                  i.created_at = datetime()
                    ON MATCH SET i.feedback_count = coalesce(i.feedback_count, 0) + 1,
                                 i.helpful_count = coalesce(i.helpful_count, 0) + $helpful
                """, id=insight_id, helpful=1 if helpful else 0)

                # Store detailed feedback if comment provided
                if comment:
                    session.run("""
                        MATCH (i:AnalyticsInsight {id: $id})
                        CREATE (f:InsightFeedback {
                            id: randomUUID(),
                            helpful: $helpful,
                            comment: $comment,
                            created_at: datetime()
                        })
                        CREATE (f)-[:FEEDBACK_FOR]->(i)
                    """, id=insight_id, helpful=helpful, comment=comment)

            logger.info(f"Recorded feedback for insight {insight_id}: helpful={helpful}")
            return True
        except Exception as e:
            logger.error(f"Failed to record feedback: {e}")
            return False

    def get_insight_effectiveness(self) -> dict[str, float]:
        """Calculate effectiveness of different insight types.

        Returns:
            Dict mapping insight_type to effectiveness score (0-1)
        """
        try:
            with self.client.session() as session:
                result = session.run("""
                    MATCH (i:AnalyticsInsight)
                    WHERE i.feedback_count > 0
                    RETURN i.insight_type as type,
                           sum(i.helpful_count) as helpful,
                           sum(i.feedback_count) as total
                """)

                effectiveness = {}
                for record in result:
                    insight_type = record["type"]
                    helpful = record["helpful"] or 0
                    total = record["total"] or 1
                    effectiveness[insight_type] = helpful / total if total > 0 else 0.5

                return effectiveness
        except Exception as e:
            logger.warning(f"Failed to get insight effectiveness: {e}")
            return {}

    def get_improvement_suggestions(self) -> list[str]:
        """Analyze feedback patterns and suggest improvements.

        Returns:
            List of improvement suggestions
        """
        suggestions = []
        effectiveness = self.get_insight_effectiveness()

        for insight_type, score in effectiveness.items():
            if score < 0.3:
                suggestions.append(
                    f"Consider revising '{insight_type}' insights - only {score:.0%} found helpful"
                )
            elif score > 0.8:
                suggestions.append(
                    f"'{insight_type}' insights are highly effective ({score:.0%}) - consider generating more"
                )

        if not effectiveness:
            suggestions.append("No feedback recorded yet - encourage users to rate insights")

        return suggestions

    def adjust_confidence_scores(self) -> dict[str, float]:
        """Calculate adjusted confidence scores based on feedback.

        Returns:
            Dict mapping insight_type to adjusted confidence multiplier
        """
        effectiveness = self.get_insight_effectiveness()

        # Baseline confidence adjustment
        # Types with good feedback get boosted, poor feedback get reduced
        adjustments = {}
        for insight_type, score in effectiveness.items():
            if score >= 0.7:
                adjustments[insight_type] = 1.1  # Boost confidence by 10%
            elif score >= 0.5:
                adjustments[insight_type] = 1.0  # No change
            elif score >= 0.3:
                adjustments[insight_type] = 0.9  # Reduce confidence by 10%
            else:
                adjustments[insight_type] = 0.8  # Reduce confidence by 20%

        return adjustments

    def get_feedback_summary(self) -> dict:
        """Get summary of all feedback received.

        Returns:
            Summary dict with counts and effectiveness metrics
        """
        effectiveness = self.get_insight_effectiveness()
        suggestions = self.get_improvement_suggestions()

        try:
            with self.client.session() as session:
                result = session.run("""
                    MATCH (i:AnalyticsInsight)
                    WHERE i.feedback_count > 0
                    RETURN sum(i.feedback_count) as total_feedback,
                           sum(i.helpful_count) as helpful_count,
                           count(i) as insights_with_feedback
                """)

                record = result.single()
                total_feedback = record["total_feedback"] if record else 0
                helpful_count = record["helpful_count"] if record else 0
                insights_count = record["insights_with_feedback"] if record else 0

        except Exception:
            total_feedback = 0
            helpful_count = 0
            insights_count = 0

        return {
            "total_feedback": total_feedback or 0,
            "helpful_count": helpful_count or 0,
            "overall_effectiveness": helpful_count / total_feedback if total_feedback else None,
            "insights_with_feedback": insights_count or 0,
            "effectiveness_by_type": effectiveness,
            "suggestions": suggestions,
        }
