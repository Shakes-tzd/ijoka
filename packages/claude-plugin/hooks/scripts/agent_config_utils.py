#!/usr/bin/env python3
"""
Agent Configuration Detection Utilities

Detects and manages AI agent configuration files (CLAUDE.md, gemini.md, agent.md, etc.)
in a project. Used during Ijoka initialization to offer adding Python standards.

NO external dependencies - only Python stdlib.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


# Known agent configuration file patterns
AGENT_CONFIG_PATTERNS = [
    "CLAUDE.md",      # Claude Code / Anthropic
    "claude.md",      # Lowercase variant
    ".claude.md",     # Hidden variant
    "GEMINI.md",      # Google Gemini
    "gemini.md",
    ".gemini.md",
    "AGENT.md",       # Generic agent config
    "agent.md",
    ".agent.md",
    "CURSOR.md",      # Cursor IDE
    "cursor.md",
    ".cursorrules",   # Cursor rules file
    "COPILOT.md",     # GitHub Copilot
    "copilot.md",
    "AI.md",          # Generic AI config
    "ai.md",
    ".ai.md",
]


def find_agent_configs(project_dir: str) -> list[dict]:
    """
    Find all agent configuration files in a project.

    Args:
        project_dir: Root directory of the project

    Returns:
        List of dicts with keys: name, path, type, has_python_section
    """
    configs = []
    project_path = Path(project_dir)

    for pattern in AGENT_CONFIG_PATTERNS:
        config_path = project_path / pattern
        if config_path.exists() and config_path.is_file():
            config_type = _detect_config_type(pattern)
            has_python = _has_python_section(config_path)
            configs.append({
                "name": pattern,
                "path": str(config_path),
                "type": config_type,
                "has_python_section": has_python,
            })

    # Also check .claude directory
    claude_dir = project_path / ".claude"
    if claude_dir.exists():
        for md_file in claude_dir.glob("*.md"):
            has_python = _has_python_section(md_file)
            configs.append({
                "name": f".claude/{md_file.name}",
                "path": str(md_file),
                "type": "claude",
                "has_python_section": has_python,
            })

    return configs


def _detect_config_type(filename: str) -> str:
    """Detect the type of agent config from filename."""
    lower = filename.lower()
    if "claude" in lower:
        return "claude"
    elif "gemini" in lower:
        return "gemini"
    elif "cursor" in lower:
        return "cursor"
    elif "copilot" in lower:
        return "copilot"
    elif "agent" in lower or "ai" in lower:
        return "generic"
    return "unknown"


def _has_python_section(config_path: Path) -> bool:
    """Check if a config file already has a Python standards section."""
    try:
        content = config_path.read_text()
        # Check for various indicators of Python section
        patterns = [
            r"###?\s*Python",
            r"uv run",
            r"PYTHON_STANDARDS",
            r"#!/usr/bin/env.*uv",
        ]
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False
    except Exception:
        return False


def get_uv_version() -> Optional[str]:
    """Get the installed uv version."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Parse "uv 0.8.0" or similar
            match = re.search(r"uv\s+(\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
            return result.stdout.strip()
    except Exception:
        pass
    return None


def check_uv_compatibility(min_version: str = "0.8.0") -> dict:
    """
    Check if installed uv version meets minimum requirements.

    Returns:
        Dict with keys: installed, required, compatible, message
    """
    installed = get_uv_version()

    if installed is None:
        return {
            "installed": None,
            "required": min_version,
            "compatible": False,
            "message": "uv is not installed. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        }

    try:
        installed_parts = [int(x) for x in installed.split(".")]
        required_parts = [int(x) for x in min_version.split(".")]

        # Pad with zeros for comparison
        while len(installed_parts) < 3:
            installed_parts.append(0)
        while len(required_parts) < 3:
            required_parts.append(0)

        compatible = installed_parts >= required_parts

        if compatible:
            message = f"uv {installed} meets requirements (>= {min_version})"
        else:
            message = f"uv {installed} is older than required {min_version}. Upgrade with: pip install --upgrade uv"

        return {
            "installed": installed,
            "required": min_version,
            "compatible": compatible,
            "message": message
        }
    except Exception as e:
        return {
            "installed": installed,
            "required": min_version,
            "compatible": False,
            "message": f"Could not parse version: {e}"
        }


def generate_python_section(for_agent_type: str = "claude") -> str:
    """
    Generate the Python standards section to add to an agent config file.

    Args:
        for_agent_type: Type of agent (claude, gemini, cursor, etc.)

    Returns:
        Markdown section to insert
    """
    # Base section works for all agents
    section = """
### Python (CRITICAL)

**See `packages/claude-plugin/hooks/scripts/PYTHON_STANDARDS.md` for full details.**

Key rules:
- **ALWAYS use `uv run` to execute Python scripts** - never `python3` directly
- Scripts with dependencies MUST have uv shebang: `#!/usr/bin/env -S uv run --script`
- Git utilities are in `git_utils.py` (no deps) - import directly from there
- Database operations are in `graph_db_helper.py` (needs neo4j via uv)

```bash
# ✅ CORRECT
uv run script.py

# ❌ WRONG - will fail with missing dependencies
python3 script.py
```
"""
    return section.strip()


# =============================================================================
# Self-test when run directly
# =============================================================================

if __name__ == "__main__":
    print("=== Agent Config Utils Self-Test ===")
    print()

    # Test uv version detection
    uv_check = check_uv_compatibility()
    print(f"UV Check: {uv_check}")
    print()

    # Test config detection in current directory
    from git_utils import get_git_root
    git_root = get_git_root()
    if git_root:
        print(f"Git root: {git_root}")
        configs = find_agent_configs(git_root)
        print(f"Found {len(configs)} agent config(s):")
        for config in configs:
            print(f"  - {config['name']} ({config['type']}) - Python section: {config['has_python_section']}")
    else:
        print("Not in a git repository")

    print()
    print("Sample Python section:")
    print("-" * 40)
    print(generate_python_section())
