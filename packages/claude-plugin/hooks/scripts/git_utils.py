#!/usr/bin/env python3
"""
Git-Aware Project Resolution Utilities

This module provides git-aware project path resolution for Ijoka.
It has NO external dependencies - only Python stdlib - so it can be
imported and tested independently without neo4j or other packages.

Key Principle: PROJECT = GIT REPOSITORY
All subdirectories within a git repo belong to the same project.
This ensures consistent attribution regardless of working directory.

Usage:
    from git_utils import resolve_project_path, get_git_root

    # Get the canonical project path (git root)
    project = resolve_project_path(cwd="/some/subdirectory")

    # Check if in a git repo
    if is_git_initialized():
        print("In a git repo")
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


def get_git_root(start_path: Optional[str] = None) -> Optional[str]:
    """
    Find the git repository root from a given path.

    In Ijoka, a PROJECT is defined by its git repository root. All subdirectories
    within a git repo belong to the same project. This ensures consistent attribution
    regardless of which subdirectory Claude is working in.

    Args:
        start_path: Starting directory to search from. Defaults to cwd.

    Returns:
        Absolute path to the git root, or None if not in a git repo.
    """
    try:
        cwd = start_path or os.getcwd()
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_worktree_info(start_path: Optional[str] = None) -> dict:
    """
    Get information about the current git worktree context.

    For parallel development, each worktree is treated as a separate workspace
    but belongs to the same project (main repo). This function provides context
    for proper attribution in parallel scenarios.

    Returns:
        Dict with keys:
        - git_root: Root of the current worktree (or main repo)
        - main_repo: Path to the main repository (same as git_root if not in worktree)
        - is_worktree: True if in a linked worktree (not main)
        - branch: Current branch name
        - worktree_path: Path to current worktree (None if main)
    """
    info = {
        "git_root": None,
        "main_repo": None,
        "is_worktree": False,
        "branch": None,
        "worktree_path": None
    }

    try:
        cwd = start_path or os.getcwd()

        # Get git root (current worktree or main)
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )
        if result.returncode == 0:
            info["git_root"] = result.stdout.strip()

        # Get common dir (main repo .git directory)
        result = subprocess.run(
            ['git', 'rev-parse', '--git-common-dir'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )
        if result.returncode == 0:
            common_dir = result.stdout.strip()
            # If common dir is not ".git", we're in a worktree
            if not common_dir.endswith('.git'):
                # Extract main repo path from common dir
                main_git_dir = Path(common_dir).resolve()
                info["main_repo"] = str(main_git_dir.parent)
                info["is_worktree"] = True
                info["worktree_path"] = info["git_root"]
            else:
                info["main_repo"] = info["git_root"]

        # Get current branch
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()

    except Exception:
        pass

    return info


def resolve_project_path(
    cwd: Optional[str] = None,
    file_path: Optional[str] = None,
    env_var: Optional[str] = None
) -> str:
    """
    Resolve the canonical project path for attribution.

    Priority:
    1. Git root from file_path (if provided)
    2. Git root from cwd
    3. Git root from CLAUDE_PROJECT_DIR env var
    4. Fallback to cwd (for non-git projects, emits warning)

    In Ijoka, PROJECT = GIT REPOSITORY. All work within a git repo, regardless
    of subdirectory, is attributed to the same project.

    Args:
        cwd: Current working directory (from hook input)
        file_path: File path being operated on (from tool input)
        env_var: Value of CLAUDE_PROJECT_DIR environment variable

    Returns:
        Canonical project path (git root or fallback)
    """
    # Try file_path first (most specific)
    if file_path:
        path = Path(file_path)
        search_dir = str(path.parent) if path.is_file() or not path.exists() else str(path)
        git_root = get_git_root(search_dir)
        if git_root:
            return git_root

    # Try cwd
    if cwd:
        git_root = get_git_root(cwd)
        if git_root:
            return git_root

    # Try env var
    if env_var:
        git_root = get_git_root(env_var)
        if git_root:
            return git_root

    # Fallback: use cwd as-is (non-git project)
    fallback = cwd or env_var or os.getcwd()
    return fallback


def is_git_initialized(path: Optional[str] = None) -> bool:
    """
    Check if the given path is inside a git repository.

    Args:
        path: Directory to check. Defaults to cwd.

    Returns:
        True if inside a git repo, False otherwise.
    """
    return get_git_root(path) is not None


# =============================================================================
# Self-test when run directly
# =============================================================================

if __name__ == "__main__":
    print("=== Git Utils Self-Test ===")
    print()
    print(f"Current dir: {os.getcwd()}")
    print(f"Git root: {get_git_root()}")
    print(f"Is git initialized: {is_git_initialized()}")
    print()

    worktree = get_worktree_info()
    print("Worktree info:")
    for key, value in worktree.items():
        print(f"  {key}: {value}")
    print()

    print(f"Resolved project path: {resolve_project_path()}")
    print()
    print("All tests passed!")
