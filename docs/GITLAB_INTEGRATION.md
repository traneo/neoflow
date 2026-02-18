# GitLab Integration

Complete guide to integrating and indexing GitLab repositories with NeoFlow.

## Table of Contents

- [Overview](#overview)
- [Setup](#setup)
- [Configuration](#configuration)
- [Indexing Process](#indexing-process)
- [Usage](#usage)
- [Advanced Topics](#advanced-topics)
- [Troubleshooting](#troubleshooting)

## Overview

NeoFlow integrates with GitLab to index code repositories, enabling semantic code search across your organization's codebase.

### Key Features

- **Automatic Indexing**: Index configured repositories with one command
- **Smart Chunking**: Code-aware splitting with overlap for context
- **Metadata Extraction**: Extracts imports, definitions, and structure
- **Test Detection**: Identifies and marks test files
- **Incremental Updates**: Refresh specific repositories
- **Live Search**: Fallback to real-time GitLab API search

## Setup

### Prerequisites

1. GitLab instance (cloud or self-hosted)
2. Personal Access Token with `read_api` and `read_repository` scopes
3. Group or project access

### Create Access Token

1. Go to GitLab Profile Settings → Access Tokens
2. Create token with scopes:
   - `read_api`
   - `read_repository`
3. Copy token (shown once!)

### Configure NeoFlow

Set environment variable:

```bash
export GITLAB_TOKEN=glpat-your_token_here
```

Or in `.env`:
```
GITLAB_TOKEN=glpat-your_token_here
```

### Configure Repositories

Create `gitlab_repos.yaml` in project root:

```yaml
repositories:
  - name: backend-api
    path: mygroup/backend-api
    enabled: true
    
  - name: frontend-app
    path: mygroup/frontend-app
    enabled: true
    
  - name: shared-lib
    path: mygroup/shared-library
    enabled: false  # Skip this one
```

## Configuration

### GitLab Settings

In [config.py](../neoflow/config.py):

```python
@dataclass
class GitLabConfig:
    base_url: str = "https://gitlab.com/api/v4"
    api_token: str = ""
    gitlab_group_path: str = "mygroup/"
    max_file_size_bytes: int = 1_000_000  # 1MB
    repos_config_path: str = "gitlab_repos.yaml"
    allowed_extensions: tuple[str, ...] = (
        ".py", ".js", ".ts", ".java", ".go", ".md",
        ".yaml", ".yml", ".json", ".xml", ".sql",
    )
    live_search_keywords: tuple[str, ...] = (
        "gitlab:", "repository:", "repo:", "project:",
    )
```

### Environment Variables

```bash
# GitLab API endpoint
GITLAB_BASE_URL=https://gitlab.com/api/v4

# Access token
GITLAB_TOKEN=glpat-...

# Group path prefix
GITLAB_GROUP_PATH=MyOrganization/

# Repository config file
GITLAB_REPOS_CONFIG=gitlab_repos.yaml
```

### Repository Configuration

**gitlab_repos.yaml:**

```yaml
repositories:
  # Repository name (for display)
  - name: backend-api
    # Full project path in GitLab
    path: mygroup/backend-api
    # Enable/disable indexing
    enabled: true
    # Optional: specific branch (default: main)
    branch: main
    # Optional: subdirectories to index (default: all)
    include_paths:
      - src/
      - lib/
    # Optional: paths to exclude
    exclude_paths:
      - tests/fixtures/
      - legacy/
```

## Indexing Process

### How It Works

```
1. Fetch Repository List
   ↓
2. For Each Enabled Repo:
   ├── Download Repository Archive (ZIP)
   ├── Extract Files
   ├── Filter by Extensions
   ├── Skip Large Files
   ├── For Each File:
   │   ├── Extract Imports
   │   ├── Extract Definitions
   │   ├── Detect if Test
   │   ├── Chunk Code (with overlap)
   │   └── Generate Embeddings
   └── Store in Weaviate
   ↓
3. Index Complete
```

### Smart Chunking

Code is split intelligently:

- **Chunk Size**: ~2000 bytes (configurable)
- **Overlap**: 2 lines between chunks for context
- **Function Aware**: Tries to keep functions intact
- **Context Preserved**: Includes file path, line numbers

### Metadata Extraction

For each code chunk:

**Imports:**
```python
# Extracts from patterns like:
import module
from package import name
require('module')
#include <header>
using namespace;
```

**Definitions:**
```python
# Extracts from patterns like:
class ClassName
function functionName
def function_name
func functionName
interface InterfaceName
type TypeName
struct StructName
enum EnumName
```

**Test Detection:**
```python
# Identifies test files by:
- Path contains /test/
- Filename like *_test.py
- Filename like *.test.js
- Filename like *.spec.ts
```

### Weaviate Schema

**Code Collection:**

```python
{
  "name": "Code",
  "properties": [
    # Vectorized (searchable)
    "content",          # Code chunk text
    
    # Metadata (not vectorized)
    "file_path",        # Full path in repo
    "repository",       # Repository name
    "language",         # Programming language
    "chunk_index",      # Chunk number
    "total_chunks",     # Total chunks for file
    "line_start",       # Starting line number
    "line_end",         # Ending line number
    "imports",          # Extracted imports (list)
    "definitions",      # Extracted definitions (list)
    "is_test"           # Test file flag
  ]
}
```

## Usage

### Index All Repositories

```bash
neoflow gitlab-index
```

**Output:**
```
Indexing GitLab repositories...
✓ backend-api: 156 files indexed
✓ frontend-app: 203 files indexed
GitLab indexing complete.
```

### Refresh One Repository

```bash
neoflow gitlab-refresh backend-api
```

Re-indexes a single repository (clears old data first).

### Refresh All Repositories

```bash
neoflow gitlab-refresh
```

### List Configured Repositories

```bash
neoflow gitlab-list
```

**Output:**
```
Configured GitLab Repositories:
  ✓ backend-api (mygroup/backend-api) - enabled
  ✓ frontend-app (mygroup/frontend-app) - enabled
  ✗ old-service (mygroup/old-service) - disabled
```

### Search Indexed Code

After indexing, use search:

```bash
neoflow search -q "JWT authentication implementation"
```

Interactive mode:
```bash
$ neoflow
You: How is authentication implemented?
[Searches indexed code automatically]
```

### Live GitLab Search

For repositories not indexed or real-time searches:

```bash
$ neoflow
You: gitlab: authentication in backend-api
[Performs live GitLab API search]
```

Or programmatically:
```json
{
  "action": "gitlab_live_search",
  "keywords": ["authentication", "JWT"],
  "repos": ["backend-api"]
}
```

## Advanced Topics

### File Filtering

**Included by Default:**
- Code files (see `allowed_extensions`)
- Documentation (`.md`)
- Configuration (`.yaml`, `.json`, `.xml`)

**Excluded by Default:**
- Large files (>1MB)
- Binary files
- Lock files (`package-lock.json`, etc.)
- Generated files (`*.min.js`, `*.bundle.js`)
- Common ignore directories (`node_modules`, `.git`, etc.)

### Custom Filters

Modify `config.py`:

```python
@dataclass
class GitLabConfig:
    # Add more extensions
    allowed_extensions: tuple[str, ...] = (
        ".py", ".js", ".ts",
        ".rb",  # Add Ruby
        ".php", # Add PHP
        # ...
    )
    
    # Increase max file size
    max_file_size_bytes: int = 2_000_000  # 2MB
```

### Chunk Size Tuning

In `LLMProviderConfig`:

```python
chunk_size_bytes: int = 2_000  # Default

# For more context per chunk:
chunk_size_bytes: int = 3_000

# For more granular search:
chunk_size_bytes: int = 1_500
```

**Trade-offs:**
- Larger chunks: More context, fewer results, slower
- Smaller chunks: More precise, more results, faster

### Branch Selection

In `gitlab_repos.yaml`:

```yaml
repositories:
  - name: backend-api
    path: mygroup/backend-api
    branch: develop  # Index develop branch instead of main
    enabled: true
```

### Private Repositories

Works automatically if your token has access to private repos. Ensure token has:
- `read_api` scope
- `read_repository` scope
- User is member of repository/group

### Self-Hosted GitLab

Configure base URL:

```bash
export GITLAB_BASE_URL=https://gitlab.mycompany.com/api/v4
```

Or in `config.py`:

```python
gitlab.base_url = "https://gitlab.mycompany.com/api/v4"
```

## Performance

### Indexing Speed

Factors affecting speed:
- Repository size
- Number of files
- Network speed
- Embedding generation speed (LLM)

**Typical Performance:**
- Small repo (<50 files): 30 seconds
- Medium repo (50-200 files): 2-5 minutes
- Large repo (>500 files): 10-20 minutes

### Parallel Processing

Indexing uses parallel processing:
- Multiple files processed simultaneously
- Batch embedding generation
- Configurable workers (default: 4)

### Search Performance

After indexing:
- Code search: <1 second (typical)
- Complex queries: 1-3 seconds
- Live GitLab search: 3-5 seconds

## Troubleshooting

### "GITLAB_TOKEN not set"

```bash
export GITLAB_TOKEN=glpat-your_token
```

Verify:
```bash
echo $GITLAB_TOKEN
```

### "Repository not found"

**Check:**
1. Token has access to repository
2. Path is correct in `gitlab_repos.yaml`
3. Repository exists and isn't archived

### "Permission Denied"

**Solutions:**
1. Regenerate token with correct scopes
2. Ensure user is member of group/project
3. Check private repository access

### No Search Results

**After indexing, check:**
1. Indexing completed successfully
2. Files were actually indexed (check logs)
3. Search query matches indexed content

### Slow Indexing

**Optimize:**
1. Reduce `max_file_size_bytes` to skip large files
2. Exclude unnecessary directories
3. Index smaller set of repositories first
4. Check network connection

### Incomplete Indexing

**Check:**
1. Weaviate has enough memory
2. No network interruptions during indexing
3. Look for errors in verbose output:
   ```bash
   neoflow -v gitlab-index
   ```

### Live Search Not Working

**Verify:**
1. `GITLAB_TOKEN` is set
2. Token hasn't expired
3. Network connectivity to GitLab
4. Use live search keywords:
   ```
   gitlab: your search query
   ```

## Best Practices

### 1. Regular Re-indexing

Schedule periodic re-indexing:

```bash
# Cron job: daily at 2 AM
0 2 * * * cd /path/to/neoflow && neoflow gitlab-refresh
```

### 2. Selective Indexing

Only index repositories you actively use:

```yaml
repositories:
  - name: core-service
    path: MyOrg/core-service
    enabled: true  # Actively used
    
  - name: legacy-app
    path: MyOrg/legacy-app
    enabled: false  # Rarely need
```

### 3. Monitor Index Size

Large indexes impact:
- Search performance
- Memory usage
- Embedding costs

**Strategy:**
- Index only source code directories
- Exclude test fixtures
- Skip generated files

### 4. Test Before Production

Test indexing with one repository:

```yaml
repositories:
  - name: test-repo
    path: MyOrg/small-repo
    enabled: true
```

Then expand to full list.

### 5. Use Live Search for Ad-Hoc

Don't index everything. Use live search for:
- Repositories you rarely query
- External/third-party repos
- Quick one-off searches

## See Also

- [Search Features](SEARCH_FEATURES.md)
- [Data Import](DATA_IMPORT.md)
- [Configuration](CONFIGURATION.md)
- [CLI Reference](CLI_REFERENCE.md)
