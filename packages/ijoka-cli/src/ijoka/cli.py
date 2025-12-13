"""
Ijoka CLI - Command line interface for AI agent observability.

Usage:
    ijoka status              # Get project status
    ijoka feature list        # List all features
    ijoka feature start       # Start next feature
    ijoka feature complete    # Complete current feature
"""

import json
import sys
from typing import Annotated, Optional

import typer
from loguru import logger
from rich import print as rprint
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .db import IjokaClient, get_client
from .models import (
    FeatureCategory,
    FeatureStatus,
    InsightType,
    PlanResponse,
    ProjectStats,
)
from .analytics import PatternDetector, TemporalAnalyzer, AgentProfiler, InsightSynthesizer, SelfImprovementLoop
from .query_engine import AgenticQueryEngine

# Configure loguru - only show warnings and above by default
logger.remove()
logger.add(sys.stderr, level="WARNING")

# Console for rich output
console = Console()

# Main app
app = typer.Typer(
    name="ijoka",
    help="CLI for AI agent observability and orchestration.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# Subcommand groups
feature_app = typer.Typer(help="Feature management commands")
plan_app = typer.Typer(help="Plan management commands")
insight_app = typer.Typer(help="Insight management commands")
session_app = typer.Typer(help="Session management commands")
analytics_app = typer.Typer(help="Analytics and insights commands")

app.add_typer(feature_app, name="feature")
app.add_typer(plan_app, name="plan")
app.add_typer(insight_app, name="insight")
app.add_typer(session_app, name="session")
app.add_typer(analytics_app, name="analytics")


# =============================================================================
# SHARED OPTIONS
# =============================================================================


def get_json_option():
    return typer.Option(False, "--json", "-j", help="Output as JSON")


def output_json(data: dict) -> None:
    """Print data as JSON."""
    print(json.dumps(data, indent=2, default=str))


def get_client_safe() -> IjokaClient:
    """Get client with error handling."""
    try:
        return get_client()
    except Exception as e:
        console.print(f"[red]Error connecting to database:[/red] {e}")
        raise typer.Exit(1)


# =============================================================================
# STATUS COMMAND (Top Level)
# =============================================================================


@app.command()
def status(
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
    insights: Annotated[bool, typer.Option("--insights", "-i", help="Include recent insights")] = False,
    blockers: Annotated[bool, typer.Option("--blockers", "-b", help="Include blocked features")] = False,
):
    """
    Get current project status.

    Shows project overview, active feature, and progress stats.
    """
    client = get_client_safe()

    try:
        project = client.ensure_project()
        stats = client.get_stats()
        active_feature = client.get_active_feature()
        active_session = client.get_active_session()

        if json_output:
            data = {
                "success": True,
                "project": {"id": project.id, "name": project.name, "path": project.path},
                "stats": stats.model_dump(),
                "current_feature": active_feature.model_dump() if active_feature else None,
                "active_session": active_session.model_dump() if active_session else None,
            }
            if insights:
                data["insights"] = [i.model_dump() for i in client.list_insights(limit=5)]
            output_json(data)
            return

        # Rich output
        console.print()
        console.print(Panel(
            f"[bold]{project.name}[/bold]\n{project.path}",
            title="Project",
            border_style="blue",
        ))

        # Stats
        _print_stats(stats)

        # Active feature
        if active_feature:
            console.print()
            console.print(Panel(
                f"[bold]{active_feature.description}[/bold]\n"
                f"Category: {active_feature.category.value} | Priority: {active_feature.priority}",
                title="Current Feature",
                border_style="green",
            ))
        else:
            console.print()
            console.print("[yellow]No active feature. Run 'ijoka feature start' to begin.[/yellow]")

        # Insights
        if insights:
            insight_list = client.list_insights(limit=5)
            if insight_list:
                console.print()
                console.print("[bold]Recent Insights:[/bold]")
                for ins in insight_list:
                    console.print(f"  • [{ins.pattern_type.value}] {ins.description[:60]}...")

    finally:
        client.close()


def _print_stats(stats: ProjectStats) -> None:
    """Print stats in a formatted way."""
    console.print()
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    table.add_row("Progress", f"{stats.complete}/{stats.total} ({stats.completion_percentage}%)")
    table.add_row("Pending", str(stats.pending))
    table.add_row("In Progress", str(stats.in_progress))
    table.add_row("Blocked", str(stats.blocked))
    table.add_row("Complete", str(stats.complete))

    console.print(table)


# =============================================================================
# FEATURE COMMANDS
# =============================================================================


@feature_app.command("list")
def feature_list(
    status_filter: Annotated[Optional[str], typer.Option("--status", "-s", help="Filter by status")] = None,
    category_filter: Annotated[Optional[str], typer.Option("--category", "-c", help="Filter by category")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """List all features with optional filtering."""
    client = get_client_safe()

    try:
        features = client.list_features(status=status_filter, category=category_filter)
        stats = client.get_stats()

        if json_output:
            output_json({
                "success": True,
                "features": [f.model_dump() for f in features],
                "count": len(features),
                "stats": stats.model_dump(),
            })
            return

        # Rich table output
        console.print()
        table = Table(title=f"Features ({len(features)})")
        table.add_column("Status", width=3)
        table.add_column("Pri", justify="right", width=4)
        table.add_column("Category", width=14)
        table.add_column("Description")

        status_icons = {
            FeatureStatus.COMPLETE: "[green]✓[/green]",
            FeatureStatus.IN_PROGRESS: "[blue]→[/blue]",
            FeatureStatus.PENDING: "[dim]○[/dim]",
            FeatureStatus.BLOCKED: "[red]✗[/red]",
        }

        for f in features:
            icon = status_icons.get(f.status, "?")
            table.add_row(
                icon,
                str(f.priority),
                f.category.value,
                f.description[:60] + ("..." if len(f.description) > 60 else ""),
            )

        console.print(table)
        console.print()
        console.print(f"[dim]Legend: ✓ complete | → in_progress | ○ pending | ✗ blocked[/dim]")

    finally:
        client.close()


@feature_app.command("show")
def feature_show(
    feature_id: Annotated[str, typer.Argument(help="Feature ID")],
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Show details of a specific feature."""
    client = get_client_safe()

    try:
        feature = client.get_feature(feature_id)
        if not feature:
            console.print(f"[red]Feature not found: {feature_id}[/red]")
            raise typer.Exit(1)

        if json_output:
            output_json({"success": True, "feature": feature.model_dump()})
            return

        console.print()
        console.print(Panel(
            f"[bold]{feature.description}[/bold]\n\n"
            f"ID: {feature.id}\n"
            f"Category: {feature.category.value}\n"
            f"Status: {feature.status.value}\n"
            f"Priority: {feature.priority}\n"
            f"Work Count: {feature.work_count}\n"
            + (f"Assigned: {feature.assigned_agent}\n" if feature.assigned_agent else "")
            + (f"Block Reason: {feature.block_reason}\n" if feature.block_reason else ""),
            title="Feature Details",
            border_style="blue",
        ))

        if feature.steps:
            console.print("\n[bold]Steps:[/bold]")
            for i, step in enumerate(feature.steps, 1):
                console.print(f"  {i}. {step}")

    finally:
        client.close()


@feature_app.command("create")
def feature_create(
    category: Annotated[str, typer.Argument(help="Category (functional, ui, infrastructure, etc.)")],
    description: Annotated[str, typer.Argument(help="Feature description")],
    priority: Annotated[int, typer.Option("--priority", "-p", help="Priority (higher = more important)")] = 50,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Create a new feature."""
    # Validate category
    try:
        FeatureCategory(category)
    except ValueError:
        valid = ", ".join(c.value for c in FeatureCategory)
        console.print(f"[red]Invalid category: {category}[/red]")
        console.print(f"[dim]Valid categories: {valid}[/dim]")
        raise typer.Exit(1)

    client = get_client_safe()

    try:
        feature = client.create_feature(
            description=description,
            category=category,
            priority=priority,
        )

        if json_output:
            output_json({"success": True, "feature": feature.model_dump()})
            return

        console.print(f"[green]✓ Created feature:[/green] {feature.description}")
        console.print(f"[dim]ID: {feature.id}[/dim]")

    finally:
        client.close()


@feature_app.command("start")
def feature_start(
    feature_id: Annotated[Optional[str], typer.Argument(help="Feature ID (uses next if not specified)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Start working on a feature."""
    client = get_client_safe()

    try:
        feature = client.start_feature(feature_id=feature_id)

        if json_output:
            output_json({"success": True, "feature": feature.model_dump()})
            return

        console.print(f"[green]✓ Started:[/green] {feature.description}")
        console.print(f"[dim]ID: {feature.id}[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@feature_app.command("complete")
def feature_complete(
    feature_id: Annotated[Optional[str], typer.Argument(help="Feature ID (uses active if not specified)")] = None,
    summary: Annotated[Optional[str], typer.Option("--summary", "-s", help="Completion summary")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Mark a feature as complete."""
    client = get_client_safe()

    try:
        feature = client.complete_feature(feature_id=feature_id, summary=summary)

        if json_output:
            output_json({"success": True, "feature": feature.model_dump()})
            return

        console.print(f"[green]✓ Completed:[/green] {feature.description}")
        stats = client.get_stats()
        console.print(f"[dim]Progress: {stats.complete}/{stats.total} ({stats.completion_percentage}%)[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@feature_app.command("block")
def feature_block(
    feature_id: Annotated[str, typer.Argument(help="Feature ID")],
    reason: Annotated[str, typer.Option("--reason", "-r", help="Block reason")] = ...,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Mark a feature as blocked."""
    client = get_client_safe()

    try:
        feature = client.block_feature(feature_id=feature_id, reason=reason)

        if json_output:
            output_json({"success": True, "feature": feature.model_dump()})
            return

        console.print(f"[yellow]✗ Blocked:[/yellow] {feature.description}")
        console.print(f"[dim]Reason: {reason}[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@feature_app.command("archive")
def feature_archive(
    feature_id: Annotated[str, typer.Argument(help="Feature ID")],
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Archive (delete) a feature."""
    client = get_client_safe()

    try:
        success = client.archive_feature(feature_id=feature_id)

        if json_output:
            output_json({"success": success})
            return

        if success:
            console.print(f"[green]✓ Archived feature:[/green] {feature_id}")
        else:
            console.print(f"[red]Feature not found:[/red] {feature_id}")
            raise typer.Exit(1)

    finally:
        client.close()


@feature_app.command("update")
def feature_update(
    feature_id: Annotated[str, typer.Argument(help="Feature ID")],
    description: Annotated[Optional[str], typer.Option("--description", "-d", help="New description")] = None,
    category: Annotated[Optional[str], typer.Option("--category", "-c", help="New category")] = None,
    priority: Annotated[Optional[int], typer.Option("--priority", "-p", help="New priority")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Update a feature's properties."""
    if not any([description, category, priority]):
        console.print("[yellow]No updates specified. Use --description, --category, or --priority.[/yellow]")
        raise typer.Exit(1)

    client = get_client_safe()

    try:
        feature = client.update_feature(
            feature_id=feature_id,
            description=description,
            category=category,
            priority=priority,
        )

        if json_output:
            output_json({"success": True, "feature": feature.model_dump()})
            return

        console.print(f"[green]✓ Updated:[/green] {feature.description}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@feature_app.command("discover")
def feature_discover(
    description: Annotated[str, typer.Argument(help="Feature description")],
    category: Annotated[str, typer.Option("--category", "-c", help="Feature category")] = ...,
    priority: Annotated[int, typer.Option("--priority", "-p", help="Priority (higher = more important)")] = 50,
    steps: Annotated[Optional[list[str]], typer.Option("--step", help="Step description (can be repeated)")] = None,
    lookback_minutes: Annotated[int, typer.Option("--lookback-minutes", help="How far back to look for events")] = 60,
    mark_complete: Annotated[bool, typer.Option("--mark-complete", help="Mark feature as complete immediately")] = False,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """
    Discover and create a feature from completed work.

    Useful when you realize work should have been tracked as a feature.
    """
    # Validate category
    try:
        FeatureCategory(category)
    except ValueError:
        valid = ", ".join(c.value for c in FeatureCategory)
        console.print(f"[red]Invalid category: {category}[/red]")
        console.print(f"[dim]Valid categories: {valid}[/dim]")
        raise typer.Exit(1)

    client = get_client_safe()

    try:
        result = client.discover_feature(
            description=description,
            category=category,
            priority=priority,
            steps=steps,
            lookback_minutes=lookback_minutes,
            mark_complete=mark_complete,
        )

        if json_output:
            output_json({"success": True, **result})
            return

        feature = result["feature"]
        status_msg = "completed" if mark_complete else "started"
        console.print(f"[green]✓ Discovered and {status_msg}:[/green] {feature.description}")
        console.print(f"[dim]ID: {feature.id}[/dim]")

        if result.get("reattributed_count", 0) > 0:
            console.print(f"[dim]Reattributed {result['reattributed_count']} events[/dim]")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


# =============================================================================
# PLAN COMMANDS
# =============================================================================


@plan_app.command("set")
def plan_set(
    steps: Annotated[list[str], typer.Argument(help="Step descriptions")],
    feature_id: Annotated[Optional[str], typer.Option("--feature-id", "-f", help="Feature ID (uses active if not specified)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Set the plan (steps) for a feature."""
    client = get_client_safe()

    try:
        created_steps = client.set_plan(feature_id=feature_id, steps=steps)

        if json_output:
            output_json({
                "success": True,
                "steps": [s.model_dump() for s in created_steps],
                "count": len(created_steps),
            })
            return

        console.print(f"[green]✓ Set plan with {len(created_steps)} steps[/green]")
        for i, step in enumerate(created_steps, 1):
            console.print(f"  {i}. {step.description}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


@plan_app.command("show")
def plan_show(
    feature_id: Annotated[Optional[str], typer.Option("--feature-id", "-f", help="Feature ID (uses active if not specified)")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Show the plan for a feature with progress."""
    client = get_client_safe()

    try:
        plan = client.get_plan(feature_id=feature_id)

        if json_output:
            output_json({
                "success": True,
                "feature_id": plan["feature_id"],
                "steps": [s.model_dump() for s in plan["steps"]],
                "active_step": plan["active_step"].model_dump() if plan["active_step"] else None,
                "progress": plan["progress"],
            })
            return

        # Rich output
        console.print()
        progress = plan["progress"]
        console.print(Panel(
            f"Progress: {progress['completed']}/{progress['total']} steps ({progress['percentage']}%)",
            title=f"Plan for {plan['feature_id'][:8]}...",
            border_style="blue",
        ))

        if not plan["steps"]:
            console.print("[yellow]No steps defined[/yellow]")
            return

        console.print()
        console.print("[bold]Steps:[/bold]")
        for i, step in enumerate(plan["steps"], 1):
            status_icon = {
                "pending": "[dim]○[/dim]",
                "in_progress": "[blue]→[/blue]",
                "completed": "[green]✓[/green]",
                "skipped": "[yellow]⊘[/yellow]",
            }.get(step.status.value, "?")

            console.print(f"  {status_icon} {i}. {step.description}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    finally:
        client.close()


# =============================================================================
# CHECKPOINT COMMAND (Top Level)
# =============================================================================


@app.command()
def checkpoint(
    step_completed: Annotated[Optional[str], typer.Option("--step-completed", "-s", help="Step that was completed")] = None,
    current_activity: Annotated[Optional[str], typer.Option("--current-activity", "-a", help="Current activity")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """
    Record a checkpoint in the current work.

    Used to track progress and detect drift from the plan.
    """
    client = get_client_safe()

    try:
        result = client.checkpoint(
            step_completed=step_completed,
            current_activity=current_activity,
        )

        if json_output:
            output_json({"success": True, **result})
            return

        if result.get("warnings"):
            console.print("[yellow]Warnings:[/yellow]")
            for warning in result["warnings"]:
                console.print(f"  ⚠ {warning}")
        else:
            console.print("[green]✓ Checkpoint recorded[/green]")

    finally:
        client.close()


# =============================================================================
# INSIGHT COMMANDS
# =============================================================================


@insight_app.command("record")
def insight_record(
    pattern_type: Annotated[str, typer.Argument(help="Type: solution, anti_pattern, best_practice, tool_usage")],
    description: Annotated[str, typer.Argument(help="What was learned")],
    tags: Annotated[Optional[str], typer.Option("--tags", "-t", help="Comma-separated tags")] = None,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """Record a new insight or learning."""
    # Validate pattern type
    try:
        InsightType(pattern_type)
    except ValueError:
        valid = ", ".join(t.value for t in InsightType)
        console.print(f"[red]Invalid pattern type: {pattern_type}[/red]")
        console.print(f"[dim]Valid types: {valid}[/dim]")
        raise typer.Exit(1)

    client = get_client_safe()

    try:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        insight = client.record_insight(
            description=description,
            pattern_type=pattern_type,
            tags=tag_list,
        )

        if json_output:
            output_json({"success": True, "insight": insight.model_dump()})
            return

        console.print(f"[green]✓ Recorded insight:[/green] {description[:50]}...")
        console.print(f"[dim]ID: {insight.id}[/dim]")

    finally:
        client.close()


@insight_app.command("list")
def insight_list(
    query: Annotated[Optional[str], typer.Option("--query", "-q", help="Search query")] = None,
    tags: Annotated[Optional[str], typer.Option("--tags", "-t", help="Comma-separated tags")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Max results")] = 10,
    json_output: Annotated[bool, typer.Option("--json", "-j", help="Output as JSON")] = False,
):
    """List insights with optional filtering."""
    client = get_client_safe()

    try:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        insights = client.list_insights(query=query, tags=tag_list, limit=limit)

        if json_output:
            output_json({
                "success": True,
                "insights": [i.model_dump() for i in insights],
                "count": len(insights),
            })
            return

        console.print()
        table = Table(title=f"Insights ({len(insights)})")
        table.add_column("Type", width=12)
        table.add_column("Description")
        table.add_column("Tags", width=20)

        for ins in insights:
            table.add_row(
                ins.pattern_type.value,
                ins.description[:50] + ("..." if len(ins.description) > 50 else ""),
                ", ".join(ins.tags[:3]) if ins.tags else "",
            )

        console.print(table)

    finally:
        client.close()


# =============================================================================
# ANALYTICS COMMANDS
# =============================================================================


@analytics_app.command("patterns")
def analytics_patterns(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show discovered patterns and feature clusters."""
    client = get_client_safe()

    try:
        detector = PatternDetector(client)

        clusters = detector.detect_feature_clusters()
        workflows = detector.find_common_workflows(min_frequency=1)
        bottlenecks = detector.detect_bottlenecks()

        if json_output:
            from .models import PatternAnalysisResponse
            response = PatternAnalysisResponse(
                clusters=clusters,
                patterns=workflows,
                bottlenecks=bottlenecks
            )
            console.print_json(response.model_dump_json())
        else:
            console.print("[bold]Feature Clusters[/bold]")
            if clusters:
                for c in clusters:
                    console.print(f"  • {c.name}: {c.size} features")
            else:
                console.print("  No clusters found")

            console.print("\n[bold]Common Workflows[/bold]")
            if workflows:
                for w in workflows[:5]:
                    steps = " → ".join(w.sequence[:3])
                    if len(w.sequence) > 3:
                        steps += "..."
                    console.print(f"  • ({w.frequency}x) {steps}")
            else:
                console.print("  No common workflows found")

            console.print("\n[bold]Bottlenecks[/bold]")
            if bottlenecks:
                for b in bottlenecks[:5]:
                    severity_color = {"critical": "red", "high": "yellow", "medium": "blue", "low": "green"}.get(b.severity.value, "white")
                    console.print(f"  • [{severity_color}]{b.severity.value.upper()}[/{severity_color}] {b.description[:50]}...")
            else:
                console.print("  No bottlenecks found")
    finally:
        client.close()


@analytics_app.command("velocity")
def analytics_velocity(
    days: int = typer.Option(7, "--days", "-d", help="Time window in days"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show productivity velocity metrics."""
    client = get_client_safe()

    try:
        analyzer = TemporalAnalyzer(client)

        velocity = analyzer.compute_velocity(window_days=days)
        drift_warnings = analyzer.detect_velocity_drift()

        if json_output:
            from .models import VelocityResponse
            response = VelocityResponse(current=velocity, drift_warnings=drift_warnings)
            console.print_json(response.model_dump_json())
        else:
            console.print(f"[bold]Velocity ({days} days)[/bold]")
            console.print(f"  Features completed: {velocity.features_completed}")
            console.print(f"  Features started: {velocity.features_started}")
            if velocity.features_per_day:
                console.print(f"  Rate: {velocity.features_per_day:.2f} features/day")
            if velocity.avg_cycle_time:
                console.print(f"  Avg cycle time: {velocity.avg_cycle_time:.1f} hours")
            console.print(f"  Trend: {velocity.trend.value}")

            if drift_warnings:
                console.print("\n[bold yellow]⚠ Warnings[/bold yellow]")
                for warning in drift_warnings:
                    console.print(f"  • {warning}")
    finally:
        client.close()


@analytics_app.command("profile")
def analytics_profile(
    agent: str = typer.Option("claude-code", "--agent", "-a", help="Agent to profile"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show agent behavior profile."""
    client = get_client_safe()

    try:
        profiler = AgentProfiler(client)

        profile = profiler.build_profile(agent)

        if json_output:
            from .models import AgentProfileResponse
            response = AgentProfileResponse(profile=profile)
            console.print_json(response.model_dump_json())
        else:
            console.print(f"[bold]Agent Profile: {agent}[/bold]")
            console.print(f"  Total features: {profile.total_features}")
            console.print(f"  Completed: {profile.completed_features}")
            if profile.success_rate is not None:
                console.print(f"  Success rate: {profile.success_rate:.0%}")
            if profile.avg_completion_time:
                console.print(f"  Avg completion time: {profile.avg_completion_time:.1f} hours")
            if profile.preferred_categories:
                cats = ", ".join(c.value for c in profile.preferred_categories[:3])
                console.print(f"  Preferred categories: {cats}")
    finally:
        client.close()


@analytics_app.command("ask")
def analytics_ask(
    question: str = typer.Argument(..., help="Natural language question"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Ask a natural language question about your data."""
    client = get_client_safe()

    try:
        engine = AgenticQueryEngine(client)

        response = engine.query(question)

        if json_output:
            console.print_json(response.model_dump_json())
        else:
            console.print(f"[bold]Query Type: {response.query_type}[/bold]\n")

            if response.insights:
                console.print("[bold]Insights:[/bold]")
                for insight in response.insights[:5]:
                    console.print(f"  • {insight.description}")

            if response.data:
                console.print("\n[bold]Data:[/bold]")
                # Pretty print key metrics
                if "metrics" in response.data:
                    m = response.data["metrics"]
                    console.print(f"  Completed: {m.get('features_completed', 0)} features")
                if "count" in response.data:
                    console.print(f"  Found: {response.data['count']} items")
    finally:
        client.close()


@analytics_app.command("digest")
def analytics_digest(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show daily digest of top insights."""
    client = get_client_safe()

    try:
        synthesizer = InsightSynthesizer(client)

        insights = synthesizer.generate_daily_digest(max_insights=10)
        recommendations = synthesizer.recommend_actions()

        if json_output:
            from datetime import datetime
            from .models import DailyDigestResponse
            velocity = TemporalAnalyzer(client).compute_velocity()
            bottlenecks = PatternDetector(client).detect_bottlenecks()
            response = DailyDigestResponse(
                date=datetime.now(),
                top_insights=insights,
                velocity=velocity,
                active_bottlenecks=bottlenecks
            )
            console.print_json(response.model_dump_json())
        else:
            console.print("[bold]📊 Daily Digest[/bold]\n")

            if insights:
                console.print("[bold]Top Insights:[/bold]")
                for i, insight in enumerate(insights[:5], 1):
                    icon = {"bottleneck": "🚧", "anomaly": "⚠️", "pattern": "📈", "trend": "📉", "recommendation": "💡"}.get(insight.insight_type.value, "•")
                    console.print(f"  {icon} {insight.description}")
            else:
                console.print("  No insights available")

            if recommendations:
                console.print("\n[bold]Recommendations:[/bold]")
                for rec in recommendations[:3]:
                    console.print(f"  💡 {rec.description}")
    finally:
        client.close()


@analytics_app.command("feedback")
def analytics_feedback(
    insight_id: str = typer.Argument(..., help="Insight ID to provide feedback for"),
    helpful: bool = typer.Option(True, "--helpful/--not-helpful", help="Was the insight helpful?"),
    comment: Optional[str] = typer.Option(None, "--comment", "-c", help="Optional feedback comment"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Provide feedback on an insight to improve future recommendations."""
    client = get_client_safe()

    try:
        loop = SelfImprovementLoop(client)
        success = loop.record_feedback(insight_id, helpful, comment)

        if json_output:
            console.print_json(json.dumps({
                "success": success,
                "insight_id": insight_id,
                "helpful": helpful,
                "comment": comment
            }))
        else:
            if success:
                emoji = "👍" if helpful else "👎"
                console.print(f"{emoji} Feedback recorded for insight {insight_id[:8]}...")
                if comment:
                    console.print(f"   Comment: {comment}")
            else:
                console.print("[red]Failed to record feedback[/red]")
    finally:
        client.close()


@analytics_app.command("effectiveness")
def analytics_effectiveness(
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
) -> None:
    """Show insight effectiveness based on user feedback."""
    client = get_client_safe()

    try:
        loop = SelfImprovementLoop(client)
        summary = loop.get_feedback_summary()

        if json_output:
            console.print_json(json.dumps(summary))
        else:
            console.print("[bold]📈 Insight Effectiveness[/bold]\n")

            if summary["total_feedback"]:
                overall = summary["overall_effectiveness"]
                console.print(f"  Total feedback: {summary['total_feedback']}")
                console.print(f"  Overall effectiveness: {overall:.0%}" if overall else "  Overall effectiveness: N/A")

                if summary["effectiveness_by_type"]:
                    console.print("\n[bold]By Type:[/bold]")
                    for itype, score in summary["effectiveness_by_type"].items():
                        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                        console.print(f"  {itype}: {bar} {score:.0%}")
            else:
                console.print("  No feedback recorded yet")

            if summary["suggestions"]:
                console.print("\n[bold]Suggestions:[/bold]")
                for suggestion in summary["suggestions"]:
                    console.print(f"  • {suggestion}")
    finally:
        client.close()


# =============================================================================
# HELP COMMAND
# =============================================================================


@app.command()
def help_cmd(
    command: Annotated[Optional[str], typer.Argument(help="Command to get help for")] = None,
):
    """Show help for commands."""
    if command:
        # Get help for specific command
        if command == "feature":
            console.print(feature_app.info.help)
        elif command == "insight":
            console.print(insight_app.info.help)
        else:
            console.print(f"[dim]Run 'ijoka {command} --help' for details[/dim]")
    else:
        console.print("""
[bold]Ijoka CLI[/bold] - AI Agent Observability

[bold]Commands:[/bold]
  status              Get project status and active feature
  feature             Feature management (list, create, start, complete, etc.)
  insight             Record and search insights
  help                Show this help

[bold]Examples:[/bold]
  ijoka status                     # Project overview
  ijoka feature list               # List all features
  ijoka feature list --status pending   # Only pending
  ijoka feature start              # Start next feature
  ijoka feature complete           # Complete current
  ijoka insight record solution "..."   # Record learning

[bold]Options:[/bold]
  --json, -j          Output as JSON (for LLM/script consumption)
  --help              Show command help
        """)


# =============================================================================
# VERSION
# =============================================================================


def version_callback(value: bool):
    if value:
        from importlib.metadata import version
        try:
            v = version("ijoka")
        except Exception:
            v = "dev"
        print(f"ijoka {v}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", "-v", callback=version_callback, is_eager=True, help="Show version")
    ] = None,
):
    """
    Ijoka - CLI for AI agent observability and orchestration.

    Use 'ijoka <command> --help' for more information about a command.
    """
    pass


if __name__ == "__main__":
    app()
