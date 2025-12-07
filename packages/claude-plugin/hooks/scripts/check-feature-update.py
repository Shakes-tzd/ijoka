#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
AgentKanban Feature Update Hook
Runs after Write/Edit tool calls to detect feature_list.json changes
"""

import json
import os
import sys
import hashlib
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

SYNC_SERVER = os.environ.get("AGENTKANBAN_SERVER", "http://127.0.0.1:4000")
CACHE_DIR = Path.home() / ".cache" / "agentkanban"


def get_cache_path(project_dir: str) -> Path:
    """Get cache file path for a project's feature list hash."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    project_hash = hashlib.md5(project_dir.encode()).hexdigest()[:12]
    return CACHE_DIR / f"features_{project_hash}.json"


def load_cached_features(project_dir: str) -> dict:
    """Load cached feature state."""
    cache_path = get_cache_path(project_dir)
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except (json.JSONDecodeError, IOError):
            pass
    return {"features": [], "hash": ""}


def save_cached_features(project_dir: str, features: list, content_hash: str):
    """Save feature state to cache."""
    cache_path = get_cache_path(project_dir)
    cache_path.write_text(json.dumps({
        "features": features,
        "hash": content_hash
    }))


def send_to_server(project_dir: str, stats: dict, changed_features: list):
    """Send feature update to AgentKanban sync server."""
    try:
        data = json.dumps({
            "projectDir": project_dir,
            "stats": stats,
            "changedFeatures": changed_features
        }).encode()
        
        req = Request(
            f"{SYNC_SERVER}/events/feature-update",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (URLError, TimeoutError, OSError):
        return False


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print('{"continue": true}')
        return

    # Get project directory
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    feature_file = Path(project_dir) / "feature_list.json"
    
    # Check if feature_list.json was modified
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", tool_input.get("path", ""))
    
    if not file_path.endswith("feature_list.json"):
        print('{"continue": true}')
        return
    
    # Load current features
    if not feature_file.exists():
        print('{"continue": true}')
        return
    
    try:
        content = feature_file.read_text()
        features = json.loads(content)
        content_hash = hashlib.md5(content.encode()).hexdigest()
    except (json.JSONDecodeError, IOError) as e:
        print(json.dumps({"continue": true, "error": str(e)}))
        return
    
    # Load cached state
    cached = load_cached_features(project_dir)
    
    # Check if content changed
    if cached["hash"] == content_hash:
        print('{"continue": true}')
        return
    
    # Find changed features (newly completed)
    old_completed = {f["description"] for f in cached.get("features", []) if f.get("passes")}
    changed_features = []
    
    for feature in features:
        if feature.get("passes") and feature["description"] not in old_completed:
            changed_features.append({
                "description": feature["description"],
                "category": feature.get("category", "functional")
            })
    
    # Calculate stats
    total = len(features)
    completed = sum(1 for f in features if f.get("passes"))
    percentage = (completed / total * 100) if total > 0 else 0
    
    stats = {
        "total": total,
        "completed": completed,
        "percentage": round(percentage, 1)
    }
    
    # Send to server if there are changes
    if changed_features:
        send_to_server(project_dir, stats, changed_features)
    
    # Update cache
    save_cached_features(project_dir, features, content_hash)
    
    # Output success
    print('{"continue": true}')


if __name__ == "__main__":
    main()
