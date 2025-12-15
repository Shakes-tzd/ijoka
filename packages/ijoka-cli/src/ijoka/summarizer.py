"""
Transcript Summarizer using Claude CLI headless mode.

Generates session summaries from transcripts using Claude Haiku
via the Claude CLI in headless mode. This uses the same authentication
as the user's Claude Code installation.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# MODELS
# =============================================================================


class SessionSummary(BaseModel):
    """Generated summary of a transcript session."""
    session_id: str
    title: str = Field(description="Brief title for the session (5-10 words)")
    summary: str = Field(description="Concise summary of what was accomplished")
    key_actions: list[str] = Field(description="List of key actions taken")
    tools_highlighted: list[str] = Field(description="Most significant tools used")
    files_modified: list[str] = Field(default_factory=list, description="Key files that were modified")
    decisions_made: list[str] = Field(default_factory=list, description="Important decisions or choices made")
    tokens_used: int = Field(default=0, description="Total tokens consumed")
    model: str = Field(default="haiku", description="Model used to generate summary")


class SummaryRequest(BaseModel):
    """Request to generate a summary."""
    session_id: str
    transcript_text: str
    max_entries: int = Field(default=100, description="Max transcript entries to include")
    include_tool_details: bool = Field(default=False, description="Include tool input/output details")


# =============================================================================
# SUMMARIZER
# =============================================================================


@dataclass
class ClaudeHeadlessConfig:
    """Configuration for Claude CLI headless mode."""
    model: str = "haiku"
    max_tokens: int = 1024
    timeout_seconds: int = 60
    tools: str = ""  # Empty string disables tools


class TranscriptSummarizer:
    """
    Generates session summaries using Claude CLI in headless mode.

    Uses the same authentication as the user's Claude Code installation,
    so no separate API key is needed.
    """

    SUMMARY_PROMPT = '''Analyze this Claude Code session transcript and generate a structured summary.

<transcript>
{transcript}
</transcript>

Generate a JSON summary with this exact structure:
{{
  "title": "Brief title for the session (5-10 words)",
  "summary": "2-3 sentence summary of what was accomplished",
  "key_actions": ["action 1", "action 2", ...],
  "tools_highlighted": ["most used tool 1", "tool 2", ...],
  "files_modified": ["file1.py", "file2.ts", ...],
  "decisions_made": ["decision 1", "decision 2", ...]
}}

Focus on:
- What the user was trying to accomplish
- Key code changes or implementations
- Important decisions or architectural choices
- Files that were created or significantly modified

Return ONLY valid JSON, no markdown code blocks or explanations.'''

    def __init__(self, config: Optional[ClaudeHeadlessConfig] = None):
        """Initialize summarizer with optional config."""
        self.config = config or ClaudeHeadlessConfig()

    def _run_claude_headless(self, prompt: str) -> dict:
        """
        Run Claude CLI in headless mode and return parsed response.

        Args:
            prompt: The prompt to send to Claude

        Returns:
            Parsed JSON response from Claude

        Raises:
            RuntimeError: If Claude CLI fails or returns invalid JSON
        """
        cmd = [
            "claude",
            "-p", prompt,
            "--model", self.config.model,
            "--output-format", "json",
            "--tools", self.config.tools,  # Empty disables tools
            "--no-session-persistence",  # Don't save this as a session
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=str(Path.home()),  # Run from home to avoid project context
            )

            if result.returncode != 0:
                raise RuntimeError(f"Claude CLI failed: {result.stderr}")

            # Parse the JSON output
            response = json.loads(result.stdout)

            # Extract the assistant's text response
            if isinstance(response, dict) and "result" in response:
                text = response["result"]
            elif isinstance(response, dict) and "content" in response:
                # Handle different response formats
                content = response["content"]
                if isinstance(content, list):
                    text = "\n".join(
                        c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                else:
                    text = str(content)
            else:
                text = str(response)

            # Parse the JSON from the response text
            # Handle case where response might have markdown code blocks
            text = text.strip()
            if text.startswith("```"):
                # Remove markdown code blocks
                lines = text.split("\n")
                text = "\n".join(
                    line for line in lines
                    if not line.startswith("```")
                )

            return json.loads(text)

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timed out after {self.config.timeout_seconds}s")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse Claude response as JSON: {e}")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Is Claude Code installed?")

    def _prepare_transcript_text(
        self,
        entries: list[dict],
        max_entries: int = 100,
        include_tool_details: bool = False
    ) -> str:
        """
        Prepare transcript entries as text for summarization.

        Args:
            entries: List of transcript entry dicts
            max_entries: Maximum entries to include
            include_tool_details: Whether to include tool input/output

        Returns:
            Formatted transcript text
        """
        lines = []

        for entry in entries[:max_entries]:
            entry_type = entry.get("entry_type", "unknown")
            content = entry.get("content", "")

            if entry_type == "user":
                # Truncate long user messages
                if len(content) > 500:
                    content = content[:500] + "..."
                lines.append(f"USER: {content}")

            elif entry_type == "assistant":
                model = entry.get("model", "")
                tool_count = entry.get("tool_call_count", 0)

                # Truncate long assistant responses
                if len(content) > 1000:
                    content = content[:1000] + "..."

                model_str = f" [{model}]" if model else ""
                tools_str = f" (used {tool_count} tools)" if tool_count else ""

                lines.append(f"ASSISTANT{model_str}{tools_str}: {content}")

        return "\n\n".join(lines)

    def summarize_from_entries(
        self,
        session_id: str,
        entries: list[dict],
        max_entries: int = 100,
        include_tool_details: bool = False
    ) -> SessionSummary:
        """
        Generate a summary from transcript entries.

        Args:
            session_id: The session ID
            entries: List of transcript entry dicts from Memgraph
            max_entries: Maximum entries to include
            include_tool_details: Whether to include tool details

        Returns:
            SessionSummary with generated summary
        """
        # Prepare transcript text
        transcript_text = self._prepare_transcript_text(
            entries, max_entries, include_tool_details
        )

        if not transcript_text.strip():
            return SessionSummary(
                session_id=session_id,
                title="Empty Session",
                summary="No content to summarize.",
                key_actions=[],
                tools_highlighted=[],
            )

        # Generate summary using Claude
        prompt = self.SUMMARY_PROMPT.format(transcript=transcript_text)

        try:
            result = self._run_claude_headless(prompt)

            return SessionSummary(
                session_id=session_id,
                title=result.get("title", "Untitled Session"),
                summary=result.get("summary", ""),
                key_actions=result.get("key_actions", []),
                tools_highlighted=result.get("tools_highlighted", []),
                files_modified=result.get("files_modified", []),
                decisions_made=result.get("decisions_made", []),
                model=self.config.model,
            )
        except Exception as e:
            # Return error summary on failure
            return SessionSummary(
                session_id=session_id,
                title="Summary Generation Failed",
                summary=f"Error: {str(e)}",
                key_actions=[],
                tools_highlighted=[],
            )

    def summarize_session(self, session_id: str, project_path: Optional[str] = None) -> SessionSummary:
        """
        Generate a summary for a session from Memgraph data.

        Args:
            session_id: The session ID to summarize
            project_path: Optional project path for context

        Returns:
            SessionSummary with generated summary
        """
        import sys
        from pathlib import Path as P

        # Import graph helper
        scripts_path = P(__file__).parent.parent.parent.parent / "claude-plugin" / "hooks" / "scripts"
        if str(scripts_path) not in sys.path:
            sys.path.insert(0, str(scripts_path))

        try:
            from graph_db_helper import get_transcript_entries, is_connected
        except ImportError:
            return SessionSummary(
                session_id=session_id,
                title="Database Not Available",
                summary="Could not connect to graph database.",
                key_actions=[],
                tools_highlighted=[],
            )

        if not is_connected():
            return SessionSummary(
                session_id=session_id,
                title="Database Not Connected",
                summary="Memgraph is not connected. Run `ijoka transcript sync` first.",
                key_actions=[],
                tools_highlighted=[],
            )

        # Get entries from Memgraph
        entries = get_transcript_entries(session_id, limit=100)

        if not entries:
            return SessionSummary(
                session_id=session_id,
                title="Session Not Found",
                summary=f"No transcript data found for session {session_id}.",
                key_actions=[],
                tools_highlighted=[],
            )

        return self.summarize_from_entries(session_id, entries)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def generate_session_summary(
    session_id: str,
    model: str = "haiku",
    project_path: Optional[str] = None
) -> SessionSummary:
    """
    Generate a summary for a transcript session.

    Args:
        session_id: The session ID to summarize
        model: Claude model to use (default: haiku)
        project_path: Optional project path

    Returns:
        SessionSummary with generated summary
    """
    config = ClaudeHeadlessConfig(model=model)
    summarizer = TranscriptSummarizer(config)
    return summarizer.summarize_session(session_id, project_path)


def check_claude_cli_available() -> bool:
    """Check if Claude CLI is available."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
