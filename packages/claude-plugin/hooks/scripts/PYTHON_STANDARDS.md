# Python Standards for Ijoka Hooks

> **Minimum uv version:** 0.8.0+ (for full PEP 723 support)
> **Last validated:** 2025-12-12

## TL;DR

**ALWAYS use `uv run` to execute Python scripts. NEVER use `python3` directly.**

```bash
# ✅ CORRECT
uv run script.py
uv run --script script.py

# ❌ WRONG - will fail with missing dependencies
python3 script.py
python script.py
```

## Why uv?

[uv](https://github.com/astral-sh/uv) provides:

1. **Reproducible environments** - Dependencies declared inline in each script
2. **Automatic dependency installation** - No manual `pip install` required
3. **Isolation** - Each script gets exactly the dependencies it declares
4. **Speed** - 10-100x faster than pip, aggressive caching
5. **Cross-platform** - Works on macOS, Linux, Windows
6. **Per-script lockfiles** - Lock individual scripts with `uv lock --script`

## Script Structure

Every Python script that has external dependencies MUST follow this structure:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0", "other-package>=1.0"]
# ///
"""
Script description here.
"""

import ...
```

### Key Elements

1. **Shebang**: `#!/usr/bin/env -S uv run --script`
   - Allows script to be executed directly: `./script.py`
   - The `-S` flag passes arguments to the interpreter

2. **PEP 723 Inline Metadata**: The `# /// script` block
   - `requires-python`: Minimum Python version
   - `dependencies`: List of pip packages needed

3. **No external dependencies?** Use plain Python shebang:
   ```python
   #!/usr/bin/env python3
   ```

## Module Organization

### Dependency-Free Modules

Modules with **no external dependencies** (only Python stdlib):
- `git_utils.py` - Git operations, project resolution
- Can be tested with plain `python3`
- Can be imported by any script

### Modules with Dependencies

Modules that **require external packages**:
- `graph_db_helper.py` - Requires `neo4j`
- MUST be imported by scripts that declare the dependency
- Cannot be tested with plain `python3`

### Import Pattern

```python
# In your hook script (with uv shebang and dependencies declared):

# First, add the scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import modules
import graph_db_helper as db_helper  # needs neo4j (declared in your script)
from git_utils import resolve_project_path  # no deps, always works
```

## Testing Scripts

### Scripts with Dependencies
```bash
# Run the script through uv
uv run session-start.py

# Or with echo for stdin input
echo '{}' | uv run session-start.py
```

### Dependency-Free Modules
```bash
# Can test with plain python3
python3 git_utils.py

# Or with uv (also works)
uv run git_utils.py
```

## Common Errors

### ModuleNotFoundError: No module named 'neo4j'

**Cause**: Running with `python3` instead of `uv run`

```bash
# ❌ This fails
python3 -c "import graph_db_helper"

# ✅ This works (if run from a script with dependencies declared)
uv run session-start.py
```

**Fix**: Always use `uv run` for scripts that need external packages.

### Import fails in git_utils but works in graph_db_helper

**Cause**: Trying to import git functions from `graph_db_helper`

```python
# ❌ Wrong - git functions not exported from graph_db_helper
from graph_db_helper import resolve_project_path

# ✅ Correct - import from git_utils
from git_utils import resolve_project_path
```

## Hooks Configuration

In `hooks.json`, always invoke scripts through uv:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "uv run ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/session-start.py"
          }
        ]
      }
    ]
  }
}
```

## Adding a New Script

1. Create file with proper shebang:
   ```python
   #!/usr/bin/env -S uv run --script
   # /// script
   # requires-python = ">=3.9"
   # dependencies = ["neo4j>=5.0"]  # add your deps
   # ///
   ```

2. Add sys.path for local imports:
   ```python
   sys.path.insert(0, str(Path(__file__).parent))
   ```

3. Import what you need:
   ```python
   import graph_db_helper as db_helper
   from git_utils import resolve_project_path
   ```

4. Test with uv:
   ```bash
   uv run your-script.py
   ```

## Advanced: Per-Script Lockfiles (uv 0.8.0+)

For production scripts that need reproducible dependency versions:

```bash
# Add a dependency declaratively (modifies inline metadata)
uv add --script my-script.py requests

# Lock the script's dependencies (creates my-script.py.lock)
uv lock --script my-script.py

# Run with locked dependencies
uv run --locked my-script.py
```

This creates a `my-script.py.lock` file alongside the script, ensuring exact
dependency versions are used every time.

## Version Compatibility

| uv Version | Features |
|------------|----------|
| 0.5.x | Basic PEP 723 support |
| 0.8.0+ | `uv add --script`, `uv lock --script`, per-script lockfiles |
| Future | Python 3.14 may be auto-selected; pin versions explicitly |

**Check your version:**
```bash
uv --version
```

**Upgrade if needed:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via pip
pip install --upgrade uv
```

## References

- [uv documentation](https://docs.astral.sh/uv/)
- [uv script guide](https://docs.astral.sh/uv/guides/scripts/)
- [PEP 723 - Inline script metadata](https://peps.python.org/pep-0723/)
- [Ijoka Plugin Architecture](../../../CLAUDE.md)
