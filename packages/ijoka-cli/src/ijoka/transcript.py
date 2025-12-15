"""
Transcript Parser for Claude Code sessions.

Parses JSONL transcript files from ~/.claude/projects/ to extract:
- User messages and prompts
- Assistant responses
- Tool calls and results
- Token usage statistics
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterator, Any

from pydantic import BaseModel, Field


# =============================================================================
# TRANSCRIPT MODELS
# =============================================================================


class TokenUsage(BaseModel):
    """Token usage statistics from a single API call."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ToolCall(BaseModel):
    """A tool invocation from an assistant message."""
    id: str
    name: str
    input: dict = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result of a tool invocation."""
    tool_use_id: str
    content: str = ""
    is_error: bool = False
    stdout: Optional[str] = None
    stderr: Optional[str] = None


class TranscriptEntry(BaseModel):
    """A single entry in a transcript JSONL file."""
    type: str  # "user", "assistant", "queue-operation"
    session_id: str
    timestamp: datetime
    uuid: Optional[str] = None
    parent_uuid: Optional[str] = None
    cwd: Optional[str] = None
    git_branch: Optional[str] = None
    version: Optional[str] = None
    user_type: Optional[str] = None  # "external", "internal"
    is_sidechain: bool = False

    # For user messages
    user_content: Optional[str] = None
    tool_results: list[ToolResult] = Field(default_factory=list)

    # For assistant messages
    model: Optional[str] = None
    assistant_text: Optional[str] = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    token_usage: Optional[TokenUsage] = None
    stop_reason: Optional[str] = None

    # For queue operations
    operation: Optional[str] = None  # "enqueue", "dequeue"


class TranscriptSummary(BaseModel):
    """Summary statistics for a transcript session."""
    session_id: str
    project_path: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_minutes: Optional[float] = None

    # Message counts
    user_message_count: int = 0
    assistant_message_count: int = 0
    tool_call_count: int = 0

    # Token usage (aggregated)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0

    # Models used
    models_used: list[str] = Field(default_factory=list)

    # Git context
    git_branches: list[str] = Field(default_factory=list)

    # Tool breakdown
    tools_used: dict[str, int] = Field(default_factory=dict)  # tool_name -> count

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens


# =============================================================================
# TRANSCRIPT PARSER
# =============================================================================


class TranscriptParser:
    """
    Parser for Claude Code transcript JSONL files.

    Transcripts are stored at: ~/.claude/projects/{encoded-path}/{session-id}.jsonl
    Each line is a JSON object representing a conversation event.
    """

    CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

    def __init__(self, project_path: Optional[str] = None):
        """
        Initialize parser for a specific project.

        Args:
            project_path: Absolute path to the project directory.
                         If None, uses current working directory.
        """
        self.project_path = project_path or os.getcwd()
        self._encoded_path = self._encode_project_path(self.project_path)
        self._transcript_dir = self.CLAUDE_PROJECTS_DIR / self._encoded_path

    @staticmethod
    def _encode_project_path(path: str) -> str:
        """
        Encode a project path to Claude's directory naming format.

        /Users/shakes/DevProjects/ijoka -> -Users-shakes-DevProjects-ijoka
        """
        # Normalize and make absolute
        path = os.path.abspath(os.path.expanduser(path))
        # Replace / with -
        encoded = path.replace("/", "-")
        return encoded

    @staticmethod
    def _decode_project_path(encoded: str) -> str:
        """
        Decode Claude's directory name back to a project path.

        -Users-shakes-DevProjects-ijoka -> /Users/shakes/DevProjects/ijoka
        """
        if encoded.startswith("-"):
            return encoded.replace("-", "/", 1).replace("-", "/")
        return encoded.replace("-", "/")

    def list_sessions(self) -> list[dict]:
        """
        List all transcript sessions for this project.

        Returns:
            List of dicts with session_id, file_path, size_bytes, modified_at
        """
        sessions = []

        if not self._transcript_dir.exists():
            return sessions

        for jsonl_file in self._transcript_dir.glob("*.jsonl"):
            session_id = jsonl_file.stem
            stat = jsonl_file.stat()
            sessions.append({
                "session_id": session_id,
                "file_path": str(jsonl_file),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime),
            })

        # Sort by modified time, newest first
        sessions.sort(key=lambda x: x["modified_at"], reverse=True)
        return sessions

    @classmethod
    def list_all_projects(cls) -> list[dict]:
        """
        List all projects with transcripts.

        Returns:
            List of dicts with project_path, encoded_path, session_count
        """
        projects = []

        if not cls.CLAUDE_PROJECTS_DIR.exists():
            return projects

        for project_dir in cls.CLAUDE_PROJECTS_DIR.iterdir():
            if project_dir.is_dir():
                session_count = len(list(project_dir.glob("*.jsonl")))
                if session_count > 0:
                    projects.append({
                        "project_path": cls._decode_project_path(project_dir.name),
                        "encoded_path": project_dir.name,
                        "session_count": session_count,
                    })

        return projects

    def parse_session(self, session_id: str) -> Iterator[TranscriptEntry]:
        """
        Parse a transcript session, yielding entries.

        Args:
            session_id: The session UUID (filename without .jsonl)

        Yields:
            TranscriptEntry objects for each line
        """
        file_path = self._transcript_dir / f"{session_id}.jsonl"

        if not file_path.exists():
            raise FileNotFoundError(f"Transcript not found: {file_path}")

        with open(file_path, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    entry = self._parse_entry(data)
                    if entry:
                        yield entry
                except json.JSONDecodeError as e:
                    # Log but continue - some lines may be malformed
                    continue
                except Exception as e:
                    # Log but continue
                    continue

    def _parse_entry(self, data: dict) -> Optional[TranscriptEntry]:
        """Parse a single JSON entry into a TranscriptEntry."""
        entry_type = data.get("type")

        if entry_type == "queue-operation":
            return TranscriptEntry(
                type=entry_type,
                session_id=data.get("sessionId", ""),
                timestamp=self._parse_timestamp(data.get("timestamp")),
                operation=data.get("operation"),
            )

        if entry_type not in ("user", "assistant"):
            return None

        message = data.get("message", {})

        entry = TranscriptEntry(
            type=entry_type,
            session_id=data.get("sessionId", ""),
            timestamp=self._parse_timestamp(data.get("timestamp")),
            uuid=data.get("uuid"),
            parent_uuid=data.get("parentUuid"),
            cwd=data.get("cwd"),
            git_branch=data.get("gitBranch"),
            version=data.get("version"),
            user_type=data.get("userType"),
            is_sidechain=data.get("isSidechain", False),
        )

        if entry_type == "user":
            self._parse_user_message(entry, message)
        elif entry_type == "assistant":
            self._parse_assistant_message(entry, message)

        return entry

    def _parse_user_message(self, entry: TranscriptEntry, message: dict):
        """Extract user message content."""
        content = message.get("content")

        if isinstance(content, str):
            entry.user_content = content
        elif isinstance(content, list):
            # Content can be a list of blocks
            text_parts = []
            tool_results = []

            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif block_type == "tool_result":
                        tool_results.append(ToolResult(
                            tool_use_id=block.get("tool_use_id", ""),
                            content=block.get("content", ""),
                            is_error=block.get("is_error", False),
                        ))

            if text_parts:
                entry.user_content = "\n".join(text_parts)
            entry.tool_results = tool_results

    def _parse_assistant_message(self, entry: TranscriptEntry, message: dict):
        """Extract assistant message content, tool calls, and token usage."""
        entry.model = message.get("model")
        entry.stop_reason = message.get("stop_reason")

        # Parse token usage
        usage = message.get("usage")
        if usage:
            entry.token_usage = TokenUsage(
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
                cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
            )

        # Parse content blocks
        content = message.get("content", [])
        if isinstance(content, list):
            text_parts = []
            tool_calls = []

            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif block_type == "tool_use":
                        tool_calls.append(ToolCall(
                            id=block.get("id", ""),
                            name=block.get("name", ""),
                            input=block.get("input", {}),
                        ))
                    # Skip "thinking" blocks (encrypted)

            if text_parts:
                entry.assistant_text = "\n".join(text_parts)
            entry.tool_calls = tool_calls

    @staticmethod
    def _parse_timestamp(ts: Any) -> datetime:
        """Parse various timestamp formats."""
        if ts is None:
            return datetime.now()
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            # ISO format: 2025-12-13T10:27:57.894Z
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now()
        return datetime.now()

    def get_session_summary(self, session_id: str) -> TranscriptSummary:
        """
        Generate a summary of a transcript session.

        Args:
            session_id: The session UUID

        Returns:
            TranscriptSummary with aggregated statistics
        """
        summary = TranscriptSummary(
            session_id=session_id,
            project_path=self.project_path,
        )

        models_seen = set()
        branches_seen = set()
        tools_count: dict[str, int] = {}
        timestamps: list[datetime] = []

        for entry in self.parse_session(session_id):
            timestamps.append(entry.timestamp)

            if entry.type == "user":
                summary.user_message_count += 1

            elif entry.type == "assistant":
                summary.assistant_message_count += 1

                if entry.model:
                    models_seen.add(entry.model)

                if entry.token_usage:
                    summary.total_input_tokens += entry.token_usage.input_tokens
                    summary.total_output_tokens += entry.token_usage.output_tokens
                    summary.total_cache_creation_tokens += entry.token_usage.cache_creation_input_tokens
                    summary.total_cache_read_tokens += entry.token_usage.cache_read_input_tokens

                for tool_call in entry.tool_calls:
                    summary.tool_call_count += 1
                    tools_count[tool_call.name] = tools_count.get(tool_call.name, 0) + 1

            if entry.git_branch:
                branches_seen.add(entry.git_branch)

        # Set time range
        if timestamps:
            summary.start_time = min(timestamps)
            summary.end_time = max(timestamps)
            duration = (summary.end_time - summary.start_time).total_seconds()
            summary.duration_minutes = round(duration / 60, 2)

        summary.models_used = sorted(models_seen)
        summary.git_branches = sorted(branches_seen)
        summary.tools_used = dict(sorted(tools_count.items(), key=lambda x: -x[1]))

        return summary


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_recent_sessions(project_path: Optional[str] = None, limit: int = 10) -> list[dict]:
    """
    Get recent transcript sessions for a project.

    Args:
        project_path: Project directory (defaults to cwd)
        limit: Maximum number of sessions to return

    Returns:
        List of session info dicts
    """
    parser = TranscriptParser(project_path)
    sessions = parser.list_sessions()
    return sessions[:limit]


def get_session_cost_estimate(summary: TranscriptSummary) -> dict:
    """
    Estimate API cost for a session based on token usage.

    Uses approximate pricing (may not be current):
    - Claude Opus: $15/M input, $75/M output
    - Claude Sonnet: $3/M input, $15/M output
    - Claude Haiku: $0.25/M input, $1.25/M output

    Returns:
        Dict with estimated costs per model tier
    """
    input_tokens = summary.total_input_tokens
    output_tokens = summary.total_output_tokens

    # Cost per million tokens
    pricing = {
        "opus": {"input": 15.0, "output": 75.0},
        "sonnet": {"input": 3.0, "output": 15.0},
        "haiku": {"input": 0.25, "output": 1.25},
    }

    estimates = {}
    for tier, prices in pricing.items():
        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]
        estimates[tier] = {
            "input_cost": round(input_cost, 4),
            "output_cost": round(output_cost, 4),
            "total_cost": round(input_cost + output_cost, 4),
        }

    return estimates


# =============================================================================
# GRAPH DATABASE SYNC
# =============================================================================


def sync_transcript_to_graph(
    parser: TranscriptParser,
    session_id: str,
    clear_existing: bool = False
) -> dict:
    """
    Sync a parsed transcript session to Memgraph.

    This bridges the TranscriptParser with the graph database schema,
    storing entries, tool uses, and aggregates for analytics.

    Args:
        parser: TranscriptParser instance
        session_id: Session ID to sync
        clear_existing: If True, clear existing data before sync

    Returns:
        Dict with sync statistics
    """
    # Import graph helpers (lazy import to avoid circular deps)
    import sys
    # Path: transcript.py -> ijoka -> src -> ijoka-cli -> packages -> claude-plugin/hooks/scripts
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "claude-plugin" / "hooks" / "scripts"))
    try:
        from graph_db_helper import (
            create_transcript_session,
            insert_transcript_entry,
            clear_transcript_session,
            is_connected
        )
    except ImportError:
        return {"error": "graph_db_helper not available", "synced": 0}

    if not is_connected():
        return {"error": "Memgraph not connected", "synced": 0}

    # Get transcript file info
    sessions = parser.list_sessions()
    session_info = next((s for s in sessions if s["session_id"] == session_id), None)
    if not session_info:
        return {"error": f"Session {session_id} not found", "synced": 0}

    # Clear existing if requested
    if clear_existing:
        clear_transcript_session(session_id)

    # Create/update TranscriptSession node
    create_transcript_session(
        session_id=session_id,
        project_dir=parser.project_path,
        transcript_path=session_info["file_path"],
        file_modified_at=session_info["modified_at"].isoformat()
    )

    # Parse and insert entries
    entry_count = 0
    tool_count = 0
    errors = []

    for entry in parser.parse_session(session_id):
        try:
            # Prepare tool calls list
            tool_calls = None
            if entry.tool_calls:
                tool_calls = [
                    {"id": tc.id, "name": tc.name, "input": tc.input}
                    for tc in entry.tool_calls
                ]
                tool_count += len(tool_calls)

            # Get content based on entry type
            content = entry.user_content if entry.type == "user" else entry.assistant_text

            # Get token usage
            input_tokens = 0
            output_tokens = 0
            cache_creation_tokens = 0
            cache_read_tokens = 0
            if entry.token_usage:
                input_tokens = entry.token_usage.input_tokens
                output_tokens = entry.token_usage.output_tokens
                cache_creation_tokens = entry.token_usage.cache_creation_input_tokens
                cache_read_tokens = entry.token_usage.cache_read_input_tokens

            insert_transcript_entry(
                session_id=session_id,
                entry_type=entry.type,
                timestamp=entry.timestamp.isoformat(),
                uuid=entry.uuid,
                parent_uuid=entry.parent_uuid,
                content=content,
                model=entry.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_creation_tokens=cache_creation_tokens,
                cache_read_tokens=cache_read_tokens,
                tool_calls=tool_calls,
                stop_reason=entry.stop_reason,
                is_sidechain=entry.is_sidechain
            )
            entry_count += 1

        except Exception as e:
            errors.append(str(e))
            if len(errors) > 10:
                break

    return {
        "session_id": session_id,
        "entries_synced": entry_count,
        "tool_uses_synced": tool_count,
        "errors": errors[:5] if errors else [],
        "success": len(errors) == 0
    }


def sync_all_transcripts_to_graph(
    project_path: Optional[str] = None,
    limit: int = 100,
    clear_existing: bool = False
) -> dict:
    """
    Sync all transcript sessions to Memgraph.

    Args:
        project_path: Project directory (defaults to cwd)
        limit: Maximum sessions to sync
        clear_existing: If True, clear existing data before sync

    Returns:
        Dict with overall sync statistics
    """
    parser = TranscriptParser(project_path)
    sessions = parser.list_sessions()[:limit]

    results = {
        "total_sessions": len(sessions),
        "synced": 0,
        "failed": 0,
        "total_entries": 0,
        "total_tool_uses": 0,
        "errors": []
    }

    for session_info in sessions:
        result = sync_transcript_to_graph(
            parser=parser,
            session_id=session_info["session_id"],
            clear_existing=clear_existing
        )

        if result.get("success"):
            results["synced"] += 1
            results["total_entries"] += result.get("entries_synced", 0)
            results["total_tool_uses"] += result.get("tool_uses_synced", 0)
        else:
            results["failed"] += 1
            if result.get("error"):
                results["errors"].append(f"{session_info['session_id'][:8]}: {result['error']}")

    return results
