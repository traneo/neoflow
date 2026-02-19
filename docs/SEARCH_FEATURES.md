# Search Features

Comprehensive guide to NeoFlow's semantic and hybrid search capabilities.

## Table of Contents

- [Overview](#overview)
- [Search Types](#search-types)
- [How It Works](#how-it-works)
- [Usage](#usage)
- [Search Tools](#search-tools)
- [Best Practices](#best-practices)
- [Examples](#examples)

## Overview

NeoFlow provides powerful search capabilities across code, documentation, and support tickets using semantic embeddings and hybrid search (combining vector similarity with keyword matching).

### Key Features

- **Semantic Search**: Understands meaning, not just keywords
- **Hybrid Search**: Combines vector and keyword search
- **Multi-Source**: Search across code, docs, and tickets
- **Fast**: Optimized queries with Weaviate
- **Contextual**: Includes surrounding context in results
- **Ranked**: Results ordered by relevance

## Search Types

### 1. Code Search

Search indexed GitLab repositories.

**Data Indexed:**
- Source code files
- Import statements
- Function/class definitions
- File metadata
- Test file indicators

**Best For:**
- Finding implementations
- Locating specific functions/classes
- Understanding code patterns
- Cross-referencing dependencies

### 2. Documentation Search

Search documentation content.

**Data Indexed:**
- Markdown files
- API documentation
- Guides and tutorials
- Technical specifications

**Best For:**
- Learning how systems work
- Finding usage examples
- Understanding architecture
- Policy and standards

### 3. Ticket Search

Search support tickets and comments.

**Data Indexed:**
- Ticket titles and questions
- Comments and responses
- Ticket references
- Metadata (URLs, etc.)

**Best For:**
- Finding similar issues
- Learning from past solutions
- Understanding common problems
- Troubleshooting

### 4. Global Search

Search all workspace files (not just indexed).

**Best For:**
- Finding files by name or content
- Searching configuration files
- Locating specific text strings
- Quick workspace exploration

### 5. GitLab Live Search

Real-time search in GitLab repositories (fallback when not indexed).

**Best For:**
- Searching repositories not yet indexed
- Finding very recent code
- Cross-repository searches

## How It Works

### Indexing Pipeline

```
1. Source Data (Files/Tickets/Docs)
        ↓
2. Chunking (smart code-aware splitting)
        ↓
3. Embedding Generation (Ollama/OpenAI)
        ↓
4. Store in Weaviate (with metadata)
        ↓
5. Ready for Search
```

### Search Pipeline

```
1. User Query
        ↓
2. Generate Query Embedding
        ↓
3. Weaviate Hybrid Search
   - Vector similarity (semantic)
   - BM25 keyword matching
        ↓
4. Rank and Filter Results
        ↓
5. Return with Context
```

### Hybrid Search

Combines two approaches:

**Vector Search (Semantic):**
- Understands meaning
- Finds conceptually similar content
- Language-agnostic

**Keyword Search (BM25):**
- Exact term matching
- Good for specific names/IDs
- Fast and precise

**Result:** Best of both worlds!

## Usage

### CLI Search

```bash
# Interactive
neoflow search

# Direct query
neoflow search -q "JWT authentication"

# With project filter
neoflow search -q "auth" -p "backend"

# Save results
neoflow search -q "API docs" -o api_reference
```

### Interactive Mode

```bash
$ neoflow
You: How do I implement caching?
[Automatically searches and synthesizes answer]
```

### Agent Mode

```bash
neoflow agent "Find and fix the caching bug"
# Agent uses search tools automatically
```

### API

```bash
curl -X POST http://localhost:9720/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "authentication examples"}'
```

## Search Tools

### search_code

```json
{
  "action": "search_code",
  "query": "authentication middleware",
  "limit": 5
}
```

**Returns:**
```json
{
  "results": [
    {
      "file_path": "backend/middleware/auth.py",
      "line_start": 45,
      "line_end": 78,
      "content": "class AuthMiddleware...",
      "imports": ["jwt", "fastapi"],
      "definitions": ["AuthMiddleware"],
      "is_test": false,
      "similarity": 0.92
    }
  ]
}
```

### search_documentation

```json
{
  "action": "search_documentation",
  "query": "authentication setup guide",
  "limit": 3
}
```

**Returns:**
```json
{
  "results": [
    {
      "title": "Authentication Guide",
      "content": "To set up authentication...",
      "source": "docs/auth.md",
      "similarity": 0.88
    }
  ]
}
```

### search_tickets

```json
{
  "action": "search_tickets",
  "query": "login failed error 401",
  "limit": 3
}
```

**Returns:**
```json
{
  "results": [
    {
      "reference": "TICKET-10234",
      "title": "Login fails with 401",
      "question": "Users getting 401 error on login...",
      "url": "https://support.../10234",
      "comments_count": 5,
      "similarity": 0.91
    }
  ]
}
```

### get_full_ticket

Retrieve complete ticket details including ALL comments for deep research.

```json
{
  "action": "get_full_ticket",
  "reference": "TICKET-10234"
}
```

**Returns:**
```
╔═══════════════════════════════════════════════════════════════════
║ FULL TICKET DETAILS: TICKET-10234
╠═══════════════════════════════════════════════════════════════════
║ Title: Login fails with 401
║ URL: https://support.../10234
╚═══════════════════════════════════════════════════════════════════

QUESTION:
Users getting 401 error on login...

═══════════════════════════════════════════════════════════════════
COMMENTS (5):
═══════════════════════════════════════════════════════════════════

[Comment 1]
Check if the JWT token has expired...

[Comment 2]
Updated the token validation logic...
...
```

**Use Cases:**
- Follow up on relevant tickets found via `search_tickets`
- Deep dive into ticket conversation threads
- Understand complete context of support issues
- Review all comments and solutions

**Note:** Always use `get_full_ticket` after finding relevant tickets to see the complete conversation and all details.

### gitlab_live_search

```json
{
  "action": "gitlab_live_search",
  "keywords": ["authentication", "JWT"],
  "repos": ["backend-api"]
}
```

## Best Practices

### 1. Use Natural Language

**Good:**
```
"How to implement JWT token refresh?"
```

**Also Works:**
```
"JWT refresh token implementation"
```

### 2. Be Specific

**Better:**
```
"FastAPI middleware for JWT authentication"
```

**Less Effective:**
```
"authentication"
```

### 3. Use Multiple Searches

For complex queries, combine search types:
1. Search docs for concepts
2. Search code for implementations
3. Search tickets for issues

### 4. Leverage Context

Use project filters:
```bash
neoflow search -q "user model" -p "backend"
```

### 5. Adjust Result Limits

Default limits are conservative. Increase for broader context:
```json
{
  "action": "search_code",
  "query": "error handling",
  "limit": 10
}
```

## Examples

### Example 1: Find Implementation

**Query:**
```
"How is email validation implemented?"
```

**Search Flow:**
1. `search_code("email validation")`
2. Finds `validators.py` with email regex3. Returns implementation with context

### Example 2: Learn Pattern

**Query:**
```
"Show me examples of async database operations"
```

**Search Flow:**
1. `search_documentation("async database")`
2. `search_code("async def database")`
3. Returns docs + code examples

### Example 3: Troubleshooting

**Query:**
```
"Users reporting 403 errors on API calls"
```

**Search Flow:**
1. `search_tickets("403 error API")`
2. Finds similar tickets
3. `search_code("403 response")`
4. Finds error handling code
5. Synthesizes solution

### Example 4: Cross-Reference

**Query:**
```
"Where is UserService used?"
```

**Search Flow:**
1. `search_code("UserService")`
2. Finds definition
3. `search_code("import UserService")`
4. Lists all usages

## Performance Tips

### 1. Index Size

- Larger indexes = slower searches
- Use `.gitignore` patterns
- Exclude test files if not needed

### 2. Chunk Size

Adjust `chunk_size_bytes` in config:
- Larger chunks = more context, fewer results
- Smaller chunks = more precise, more results

### 3. Query Optimization

- Use specific terms for keyword boost
- Natural questions leverage semantic search
- Combine both for best results

### 4. Caching

Weaviate caches frequently accessed results.

## Troubleshooting

### No Results

**Check:**
1. Is data indexed? `neoflow gitlab-index`
2. Is Weaviate running? `docker ps`
3. Try broader query

### Irrelevant Results

**Try:**
1. More specific query
2. Use quotes for exact phrases
3. Add context/filters

### Slow Searches

**Solutions:**
1. Reduce result limit
2. Check Weaviate memory
3. Rebuild index if corrupted

### Wrong Order

Hybrid search balances semantic + keyword. If results seem off:
1. Adjust alpha parameter (in code)
2. Use more specific terms
3. Try different phrasing

## See Also

- [GitLab Integration](GITLAB_INTEGRATION.md)
- [Data Import](DATA_IMPORT.md)
- [Configuration](CONFIGURATION.md)
