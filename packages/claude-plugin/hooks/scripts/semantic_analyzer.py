#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Semantic Analyzer for Intelligent Observability

Uses Claude Code headless mode with Haiku to classify code changes and determine
when "logical units" of work are complete, enabling intelligent checkpoint and
commit suggestions.

Design Philosophy:
- Leverage intelligence, not dumb counting
- Classify changes semantically (schema, feature, bugfix, refactor, etc.)
- Detect "logical unit completion" based on understanding, not rules
- Keep latency low (~200ms with Haiku)
- Cost-efficient (~$0.001 per classification)
- Uses Claude Code CLI - no separate API key needed!
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import hashlib

# Rate limiting and caching
_CACHE_FILE = Path.home() / ".ijoka" / "semantic_cache.json"
_ANALYSIS_INTERVAL_SECONDS = 30  # Minimum time between analyses for same file
_last_analysis_times: dict[str, float] = {}


def _load_cache() -> dict:
    """Load the analysis cache."""
    try:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {"analyses": {}, "logical_units": []}


def _save_cache(cache: dict):
    """Save the analysis cache."""
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2, default=str)
    except Exception:
        pass


def _get_change_hash(file_path: str, old_string: str, new_string: str) -> str:
    """Generate a hash for a change to use as cache key."""
    content = f"{file_path}:{old_string[:100]}:{new_string[:100]}"
    return hashlib.md5(content.encode()).hexdigest()[:12]


def _should_analyze(file_path: str) -> bool:
    """Check if we should analyze this file (rate limiting)."""
    global _last_analysis_times
    now = datetime.now(timezone.utc).timestamp()
    last_time = _last_analysis_times.get(file_path, 0)

    if now - last_time < _ANALYSIS_INTERVAL_SECONDS:
        return False

    _last_analysis_times[file_path] = now
    return True


def classify_edit(
    file_path: str,
    old_string: str,
    new_string: str,
    feature_description: Optional[str] = None,
    recent_edits: Optional[list[dict]] = None
) -> dict:
    """
    Classify an edit using Claude Haiku for semantic understanding.

    Returns:
        dict with:
        - change_type: schema_change | feature_code | bugfix | refactor | docs | config | test
        - logical_unit_complete: yes | no | maybe
        - summary: Brief description of the change
        - commit_worthy: bool - should we suggest a commit?
        - checkpoint_worthy: bool - should we auto-checkpoint?
    """
    # Check cache first
    change_hash = _get_change_hash(file_path, old_string, new_string)
    cache = _load_cache()

    if change_hash in cache.get("analyses", {}):
        cached = cache["analyses"][change_hash]
        # Return cached result if less than 1 hour old
        if datetime.now(timezone.utc).timestamp() - cached.get("timestamp", 0) < 3600:
            return cached["result"]

    # Rate limit API calls
    if not _should_analyze(file_path):
        return _default_classification()

    try:
        # Build context about recent edits
        recent_context = ""
        if recent_edits:
            recent_files = list(set(e.get("file_path", "") for e in recent_edits[-5:]))
            recent_context = f"\nRecent edits in this session: {', '.join(recent_files)}"

        feature_context = ""
        if feature_description:
            feature_context = f"\nActive feature: {feature_description}"

        # Craft prompt for classification
        prompt = f"""Classify this code change for a development tracking system.

File: {file_path}
{feature_context}
{recent_context}

Change (old → new):
```
{old_string[:500]}
```
→
```
{new_string[:500]}
```

Respond in JSON only:
{{
  "change_type": "schema_change|feature_code|bugfix|refactor|docs|config|test",
  "logical_unit_complete": "yes|no|maybe",
  "summary": "brief description (max 50 chars)",
  "reasoning": "why this classification"
}}

Guidelines:
- schema_change: DB schema, API contracts, model definitions
- feature_code: New functionality implementation
- bugfix: Fixing broken behavior
- refactor: Code restructuring without behavior change
- docs: Comments, docstrings, README
- config: Configuration files, settings
- test: Test code

logical_unit_complete=yes when:
- A complete function/method is implemented
- A bug is fully fixed
- A schema migration is complete
- Tests are passing after implementation"""

        # Use Claude Code CLI in headless mode with Haiku
        # This uses existing Claude Code auth - no API key needed!
        result = subprocess.run(
            [
                "claude",
                "-p", prompt,
                "--model", "haiku",
                "--output-format", "text",
                "--max-turns", "1"
            ],
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )

        if result.returncode != 0:
            debug_log = Path.home() / ".ijoka" / "semantic_analyzer.log"
            with open(debug_log, "a") as f:
                f.write(f"{datetime.now()}: Claude CLI error: {result.stderr}\n")
            return _default_classification()

        # Parse response
        response_text = result.stdout.strip()
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        result = json.loads(response_text.strip())

        # Add derived fields
        result["commit_worthy"] = (
            result.get("change_type") in ["schema_change", "feature_code", "bugfix"] and
            result.get("logical_unit_complete") == "yes"
        )
        result["checkpoint_worthy"] = result.get("logical_unit_complete") in ["yes", "maybe"]
        result["file_path"] = file_path
        result["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Cache the result
        cache["analyses"][change_hash] = {
            "result": result,
            "timestamp": datetime.now(timezone.utc).timestamp()
        }

        # Track logical units for session summary
        if result.get("logical_unit_complete") == "yes":
            cache.setdefault("logical_units", []).append({
                "summary": result.get("summary", ""),
                "type": result.get("change_type", ""),
                "file": file_path,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            # Keep only last 20 logical units
            cache["logical_units"] = cache["logical_units"][-20:]

        _save_cache(cache)
        return result

    except Exception as e:
        # Log error but don't fail
        debug_log = Path.home() / ".ijoka" / "semantic_analyzer.log"
        with open(debug_log, "a") as f:
            f.write(f"{datetime.now()}: Error in classify_edit: {e}\n")
        return _default_classification()


def _default_classification() -> dict:
    """Return default classification when analysis is skipped or fails."""
    return {
        "change_type": "unknown",
        "logical_unit_complete": "no",
        "summary": "Change recorded",
        "commit_worthy": False,
        "checkpoint_worthy": False,
        "skipped": True
    }


def get_session_logical_units() -> list[dict]:
    """Get the logical units completed in the current session."""
    cache = _load_cache()
    return cache.get("logical_units", [])


def should_suggest_commit(session_id: str) -> tuple[bool, str]:
    """
    Determine if we should suggest a commit based on accumulated logical units.

    Returns:
        (should_suggest, reason)
    """
    cache = _load_cache()
    logical_units = cache.get("logical_units", [])

    if not logical_units:
        return False, ""

    # Count by type
    schema_changes = sum(1 for u in logical_units if u.get("type") == "schema_change")
    feature_code = sum(1 for u in logical_units if u.get("type") == "feature_code")
    bugfixes = sum(1 for u in logical_units if u.get("type") == "bugfix")

    # Suggest commit if:
    # - Any schema change (always commit schema changes)
    if schema_changes > 0:
        return True, f"Schema change detected: {logical_units[-1].get('summary', '')}"

    # - 2+ feature code logical units
    if feature_code >= 2:
        summaries = [u.get("summary", "") for u in logical_units if u.get("type") == "feature_code"][-2:]
        return True, f"Feature progress: {'; '.join(summaries)}"

    # - Any bugfix (always commit bugfixes)
    if bugfixes > 0:
        return True, f"Bug fixed: {logical_units[-1].get('summary', '')}"

    # - 3+ total logical units of any type
    if len(logical_units) >= 3:
        return True, f"{len(logical_units)} logical units completed"

    return False, ""


def generate_commit_message_suggestion() -> Optional[str]:
    """Generate a commit message suggestion based on accumulated logical units."""
    cache = _load_cache()
    logical_units = cache.get("logical_units", [])

    if not logical_units:
        return None

    # Group by type
    by_type = {}
    for unit in logical_units:
        t = unit.get("type", "unknown")
        by_type.setdefault(t, []).append(unit.get("summary", ""))

    # Generate message
    parts = []
    type_prefixes = {
        "schema_change": "schema",
        "feature_code": "feat",
        "bugfix": "fix",
        "refactor": "refactor",
        "docs": "docs",
        "config": "chore",
        "test": "test"
    }

    for change_type, summaries in by_type.items():
        prefix = type_prefixes.get(change_type, "chore")
        if len(summaries) == 1:
            parts.append(f"{prefix}: {summaries[0]}")
        else:
            parts.append(f"{prefix}: {summaries[0]} (+{len(summaries)-1} more)")

    return "; ".join(parts[:3])  # Limit to 3 parts


def clear_logical_units():
    """Clear the logical units after a commit."""
    cache = _load_cache()
    cache["logical_units"] = []
    _save_cache(cache)


def analyze_for_checkpoint(
    tool_name: str,
    tool_input: dict,
    feature_description: Optional[str] = None
) -> dict:
    """
    Main entry point for PostToolUse hook integration.
    Analyzes tool calls and returns checkpoint/commit recommendations.

    Returns:
        dict with:
        - should_checkpoint: bool
        - should_suggest_commit: bool
        - commit_reason: str (if should_suggest_commit)
        - commit_message: str (suggested message)
        - analysis: dict (classification result for Edit/Write)
    """
    result = {
        "should_checkpoint": False,
        "should_suggest_commit": False,
        "commit_reason": "",
        "commit_message": None,
        "analysis": None
    }

    # Only analyze Edit and Write tools
    if tool_name not in ("Edit", "Write"):
        return result

    file_path = tool_input.get("file_path", "")

    # Skip non-code files
    skip_patterns = [".json", ".lock", ".md", ".txt", ".log", ".csv"]
    if any(file_path.endswith(p) for p in skip_patterns):
        return result

    if tool_name == "Edit":
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")

        # Classify the edit
        analysis = classify_edit(
            file_path=file_path,
            old_string=old_string,
            new_string=new_string,
            feature_description=feature_description
        )
        result["analysis"] = analysis
        result["should_checkpoint"] = analysis.get("checkpoint_worthy", False)

    elif tool_name == "Write":
        # For new files, always checkpoint
        result["should_checkpoint"] = True
        result["analysis"] = {
            "change_type": "feature_code",
            "logical_unit_complete": "maybe",
            "summary": f"New file: {Path(file_path).name}"
        }

    # Check if we should suggest a commit
    should_commit, commit_reason = should_suggest_commit("")
    result["should_suggest_commit"] = should_commit
    result["commit_reason"] = commit_reason

    if should_commit:
        result["commit_message"] = generate_commit_message_suggestion()

    return result


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: semantic_analyzer.py <command>")
        print("Commands:")
        print("  test - Run a test classification")
        print("  units - Show logical units")
        print("  suggest - Check if commit should be suggested")
        print("  clear - Clear logical units")
        sys.exit(1)

    command = sys.argv[1]

    if command == "test":
        result = classify_edit(
            file_path="/test/example.py",
            old_string="def foo():\n    pass",
            new_string="def foo():\n    return 42",
            feature_description="Add return values to functions"
        )
        print(json.dumps(result, indent=2))

    elif command == "units":
        units = get_session_logical_units()
        print(f"Logical units: {len(units)}")
        for u in units:
            print(f"  - [{u.get('type')}] {u.get('summary')}")

    elif command == "suggest":
        should, reason = should_suggest_commit("")
        print(f"Should suggest commit: {should}")
        if reason:
            print(f"Reason: {reason}")
        msg = generate_commit_message_suggestion()
        if msg:
            print(f"Suggested message: {msg}")

    elif command == "clear":
        clear_logical_units()
        print("Logical units cleared")
