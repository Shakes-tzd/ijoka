# Ijoka CLI

CLI and SDK for AI agent observability and orchestration.

## Installation

```bash
# Using uv (recommended)
uv pip install ijoka

# Or using pip
pip install ijoka
```

## CLI Usage

```bash
# Get project status
ijoka status

# List features
ijoka feature list
ijoka feature list --status pending
ijoka feature list --category functional --json

# Manage features
ijoka feature create functional "Add user authentication"
ijoka feature start              # Start next available
ijoka feature start <id>         # Start specific feature
ijoka feature complete           # Complete current
ijoka feature block <id> --reason "Waiting for API"

# Record insights
ijoka insight record solution "Use batch processing for large datasets"
ijoka insight list --tags "performance"

# JSON output (for LLM consumption)
ijoka status --json
ijoka feature list --json
```

## SDK Usage

```python
from ijoka import IjokaClient

# Create client (auto-detects project from git root)
client = IjokaClient()

# Get project status
project = client.get_project()
stats = client.get_stats()

# List features
features = client.list_features(status="pending")
for f in features:
    print(f"{f.priority}: {f.description}")

# Manage features
feature = client.create_feature(
    description="Add user authentication",
    category="functional",
    priority=80,
)

client.start_feature(feature.id)
client.complete_feature()

# Record insights
client.record_insight(
    description="Use batch processing for large datasets",
    pattern_type="solution",
    tags=["performance", "database"],
)

# Clean up
client.close()
```

## Configuration

Set environment variables:

```bash
export IJOKA_DB_URI="bolt://localhost:7687"  # Memgraph URI
```

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Type check
uv run mypy src/ijoka

# Lint
uv run ruff check src/ijoka
```
