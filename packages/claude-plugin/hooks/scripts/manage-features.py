#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
AgentKanban Feature Manager
Deterministic feature list management - add, validate, query features.
Used by commands and hooks for consistent feature_list.json handling.
"""

import json
import sys
from pathlib import Path

VALID_CATEGORIES = {"infrastructure", "functional", "ui", "documentation", "testing", "security"}


def load_features(project_dir: str) -> tuple[list, Path]:
    """Load features from project directory."""
    feature_file = Path(project_dir) / "feature_list.json"

    if feature_file.exists():
        try:
            return json.loads(feature_file.read_text()), feature_file
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in feature_list.json: {e}")

    return [], feature_file


def save_features(features: list, feature_file: Path):
    """Save features with consistent formatting."""
    feature_file.write_text(json.dumps(features, indent=2) + "\n")


def add_feature(project_dir: str, category: str, description: str, steps: list[str] = None) -> dict:
    """Add a new feature to feature_list.json."""
    # Validate category
    if category not in VALID_CATEGORIES:
        return {
            "success": False,
            "error": f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
        }

    # Validate description
    if not description or not description.strip():
        return {"success": False, "error": "Description cannot be empty"}

    description = description.strip()

    # Load existing features
    try:
        features, feature_file = load_features(project_dir)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # Check for duplicates (case-insensitive)
    existing_descriptions = {f.get("description", "").lower() for f in features}
    if description.lower() in existing_descriptions:
        return {"success": False, "error": f"Feature already exists: {description}"}

    # Create new feature
    new_feature = {
        "category": category,
        "description": description,
        "steps": steps or [],
        "passes": False,
        "inProgress": False
    }

    # Append and save
    features.append(new_feature)
    save_features(features, feature_file)

    return {
        "success": True,
        "feature": new_feature,
        "totalFeatures": len(features)
    }


def validate_features(project_dir: str) -> dict:
    """Validate feature_list.json structure."""
    try:
        features, _ = load_features(project_dir)
    except ValueError as e:
        return {"valid": False, "error": str(e)}

    errors = []

    for i, feature in enumerate(features):
        prefix = f"Feature {i+1}"

        if not isinstance(feature, dict):
            errors.append(f"{prefix}: Not an object")
            continue

        # Required fields
        if "description" not in feature:
            errors.append(f"{prefix}: Missing 'description'")
        elif not feature["description"].strip():
            errors.append(f"{prefix}: Empty 'description'")

        if "category" not in feature:
            errors.append(f"{prefix}: Missing 'category'")
        elif feature["category"] not in VALID_CATEGORIES:
            errors.append(f"{prefix}: Invalid category '{feature['category']}'")

        if "passes" not in feature:
            errors.append(f"{prefix}: Missing 'passes'")
        elif not isinstance(feature["passes"], bool):
            errors.append(f"{prefix}: 'passes' must be boolean")

        # Optional but validated
        if "steps" in feature and not isinstance(feature["steps"], list):
            errors.append(f"{prefix}: 'steps' must be array")

        if "inProgress" in feature and not isinstance(feature["inProgress"], bool):
            errors.append(f"{prefix}: 'inProgress' must be boolean")

    # Check for duplicate descriptions
    descriptions = [f.get("description", "").lower() for f in features if isinstance(f, dict)]
    seen = set()
    for desc in descriptions:
        if desc in seen:
            errors.append(f"Duplicate description: {desc}")
        seen.add(desc)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "featureCount": len(features)
    }


def get_stats(project_dir: str) -> dict:
    """Get feature statistics."""
    try:
        features, _ = load_features(project_dir)
    except ValueError as e:
        return {"error": str(e)}

    total = len(features)
    completed = sum(1 for f in features if f.get("passes"))
    in_progress = sum(1 for f in features if f.get("inProgress"))

    by_category = {}
    for f in features:
        cat = f.get("category", "unknown")
        if cat not in by_category:
            by_category[cat] = {"total": 0, "completed": 0}
        by_category[cat]["total"] += 1
        if f.get("passes"):
            by_category[cat]["completed"] += 1

    return {
        "total": total,
        "completed": completed,
        "inProgress": in_progress,
        "remaining": total - completed,
        "percentage": round(completed / total * 100, 1) if total > 0 else 0,
        "byCategory": by_category
    }


def main():
    """CLI interface for feature management."""
    if len(sys.argv) < 2:
        print("Usage: manage-features.py <command> [args]")
        print("Commands: add, validate, stats")
        sys.exit(1)

    command = sys.argv[1]
    project_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if command == "add":
        if len(sys.argv) < 5:
            print("Usage: manage-features.py add <project_dir> <category> <description>")
            sys.exit(1)
        category = sys.argv[3]
        description = " ".join(sys.argv[4:])
        result = add_feature(project_dir, category, description)

    elif command == "validate":
        result = validate_features(project_dir)

    elif command == "stats":
        result = get_stats(project_dir)

    else:
        result = {"error": f"Unknown command: {command}"}

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success", result.get("valid", True)) else 1)


if __name__ == "__main__":
    main()
