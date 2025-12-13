# Legacy Scripts

These scripts are deprecated and not used in production. They are kept for reference only.

## Why Deprecated

- `db_helper.py` - SQLite helper, replaced by `graph_db_helper.py` (Memgraph)
- `auto-feature-match.py` - Feature matching via feature_list.json, replaced by graph DB approach
- `feature-status-manager.py` - Status management via feature_list.json, deprecated
- `validate-feature-edit.py` - Validation for feature_list.json edits, deprecated

## Migration

All feature management now uses:
- **Memgraph** as single source of truth
- **ijoka CLI** (`ijoka feature create`, `ijoka status`, etc.)
- **graph_db_helper.py** for database operations
- **git_utils.py** for project resolution

## Do Not Use

These files should not be imported or executed. They may have outdated dependencies
and incompatible data structures.
