# Data Import

Guide to importing tickets and documents into NeoFlow's vector database.

## Table of Contents

- [Overview](#overview)
- [Ticket Import](#ticket-import)
- [Data Format](#data-format)
- [Import Process](#import-process)
- [Usage](#usage)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

NeoFlow can import structured data (support tickets, bug reports, documentation) into Weaviate for semantic search.

### Supported Data Types

- **Tickets**: Support tickets with questions and comments
- **Documents**: Any structured JSON content
- **Custom**: Extend for your own data types

## Ticket Import

### Data Format

Tickets must be in JSON format:

**Single Ticket File (tickets/ticket_10001.json):**

```json
{
  "reference": "TICKET-10001",
  "question": "How do I implement JWT authentication in the API?",
  "metadata": {
    "title": "JWT Authentication Setup",
    "url": "https://support.example.com/ticket/10001"
  },
  "comments": [
    {
      "message": "You need to install the PyJWT library first..."
    },
    {
      "message": "Here's a complete example implementation..."
    }
  ]
}
```

### Weaviate Schema

**Tickets Collection:**

```python
Properties:
  - title: TEXT (vectorized)
  - question: TEXT (vectorized)
  - reference: TEXT (not vectorized, metadata)
  - url: TEXT (not vectorized, metadata)
  - chunk_index: INT (not vectorized)
  - total_chunks: INT (not vectorized)
```

**Comments Collection:**

```python
Properties:
  - message: TEXT (vectorized)
  - reference: TEXT (not vectorized, metadata)
  - chunk_index: INT (not vectorized)
  - total_chunks: INT (not vectorized)

References:
  - hasTicket: → Tickets collection
```

### Chunking

Large tickets/comments are automatically chunked:

- **Chunk Size**: ~3000 bytes
- **No Overlap**: Comments are independent
- **Metadata Preserved**: Each chunk links to parent ticket

## Import Process

### How It Works

```
1. Scan Directory (default: tickets/)
   ↓
2. For Each JSON File:
   ├── Parse JSON
   ├── Validate Schema
   ├── Check Size → Chunk if needed
   ├── Insert Ticket
   └── Insert Comments (linked to ticket)
   ↓
3. Import Complete
```

### Collection Setup

On import, collections are recreated:

```python
# Deletes existing Tickets and Comments collections
# Creates new collections with proper schema
# Inserts all data
```

**Note:** Importing is destructive (clears existing data).

## Usage

### Basic Import

```bash
neoflow import --tickets
```

Imports from default `tickets/` directory.

### Custom Directory

```bash
neoflow import --tickets
```

### Custom Batch Size

```bash
neoflow import --tickets
```

Default is 300. Adjust based on:
- Available memory
- Ticket size
- Import speed needs

### Verbose Output

```bash
neoflow -v import --tickets
```

Shows detailed progress and any errors.

### Programmatic Import

```python
from neoflow.importer.importer import import_tickets
from neoflow.config import Config

config = Config.from_env()
import_tickets(config)
```

## Best Practices

### 1. Organize Ticket Files

```
tickets/
├── ticket_10001.json
├── ticket_10002.json
├── ticket_10003.json
└── ...
```

**Naming Convention:**
- One ticket per file
- Consistent naming: `ticket_<id>.json`
- Sequential or ID-based numbering

### 2. Validate JSON

Before importing, validate JSON files:

```bash
# Check one file
python -m json.tool tickets/ticket_10001.json

# Check all files
for f in tickets/*.json; do
  echo "Checking $f"
  python -m json.tool "$f" > /dev/null || echo "Invalid: $f"
done
```

### 3. Clean Data

**Remove:**
- HTML tags
- Excessive whitespace
- Sensitive information
- Duplicate content

**Example preprocessing:**

```python
import json
import re
from pathlib import Path

def clean_ticket(ticket_data):
    # Remove HTML
    ticket_data['question'] = re.sub(r'<[^>]+>', '', ticket_data['question'])
    
    # Clean comments
    for comment in ticket_data.get('comments', []):
        comment['message'] = re.sub(r'<[^>]+>', '', comment['message'])
    
    return ticket_data

# Process all tickets
for ticket_file in Path('tickets').glob('*.json'):
    with open(ticket_file) as f:
        ticket = json.load(f)
    
    ticket = clean_ticket(ticket)
    
    with open(ticket_file, 'w') as f:
        json.dump(ticket, f, indent=2)
```

### 4. Batch Processing

For large datasets:

```bash
# Process in batches
neoflow import --tickets
neoflow import --tickets
# etc.
```

**Note:** Each import recreates collections, so this approach is only useful for testing different batches separately.

### 5. Backup Before Import

```bash
# Backup Weaviate data
# (Method depends on your Weaviate setup)

# Then import
neoflow import --tickets
```

## Advanced Topics

### Custom Data Model

Extend for your own data types:

**1. Define Model (neoflow/models.py):**

```python
from pydantic import BaseModel

class CustomDocument(BaseModel):
    title: str
    content: str
    category: str
    metadata: dict
```

**2. Create Importer (neoflow/importer/custom_importer.py):**

```python
def import_documents(config: Config):
    client = get_weaviate_client(config)
    
    # Create collection
    client.collections.create(
        name="Documents",
        vector_config=config.get_weaviate_vector_config(),
        properties=[
            Property(name="title", data_type=DataType.TEXT),
            Property(name="content", data_type=DataType.TEXT),
            Property(name="category", data_type=DataType.TEXT, 
                    skip_vectorization=True),
        ],
    )
    
    # Import data
    # ...
```

**3. Add CLI Command (neoflow/cli.py):**

```python
def cmd_import_docs(args, config: Config):
    from neoflow.importer.custom_importer import import_documents
    import_documents(config)
```

### Parallel Import

For very large datasets, parallelize:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def import_ticket_parallel(file_path, collection):
    # Process one file
    # ...

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = []
    for file_path in ticket_files:
        future = executor.submit(import_ticket_parallel, file_path, collection)
        futures.append(future)
    
    for future in as_completed(futures):
        result = future.result()
        # Handle result
```

### Incremental Updates

Instead of full re-import, update specific tickets:

```python
# Check if ticket exists
existing = collection.query.fetch_objects(
    filters=Filter.by_property("reference").equal("TICKET-10001")
)

if existing.objects:
    # Update existing
    collection.data.update(existing.objects[0].uuid, properties={...})
else:
    # Insert new
    collection.data.insert(properties={...})
```

## Troubleshooting

### Import Fails

**Check:**
1. Weaviate is running: `docker ps | grep weaviate`
2. JSON files are valid: `python -m json.tool file.json`
3. Directory exists and has files: `ls -la tickets/`

### Memory Issues

**Symptoms:**
- Import hangs
- Weaviate restarts
- Out of memory errors

**Solutions:**
1. Reduce batch size: `--batch-size 100`
2. Increase Weaviate memory in docker-compose.yaml:
   ```yaml
   weaviate:
     environment:
       - LIMIT_RESOURCES=false
     deploy:
       resources:
         limits:
           memory: 4G
   ```
3. Import in smaller batches

### Slow Import

**Optimize:**
1. Increase batch size (if memory allows)
2. Use faster embedding model
3. Disable logging during import
4. Check disk I/O (use SSD)

### Duplicate Data

**Cause:** Running import multiple times

**Solution:** Import recreates collections, so duplicates shouldn't occur. If you see duplicates:
1. Stop Weaviate
2. Delete data directory
3. Restart Weaviate
4. Re-import

### Missing Relationships

**Symptoms:** Comments not linked to tickets

**Check:**
1. Comment `hasTicket` relationship is set
2. Ticket UUID is correct
3. Comments collection has reference property

## Examples

### Example 1: Simple Ticket

```json
{
  "reference": "BUG-101",
  "question": "Application crashes when clicking logout",
  "metadata": {
    "title": "Logout Bug",
    "url": "https://issues.example.com/BUG-101"
  },
  "comments": [
    {
      "message": "This is a known issue with the session cleanup. Fix in progress."
    }
  ]
}
```

### Example 2: Feature Request

```json
{
  "reference": "FEATURE-202",
  "question": "Add support for OAuth2 authentication in addition to JWT",
  "metadata": {
    "title": "OAuth2 Support Request",
    "url": "https://issues.example.com/FEATURE-202"
  },
  "comments": [
    {
      "message": "We're evaluating this feature. OAuth2 would require significant changes to our auth flow."
    },
    {
      "message": "Implementation plan: 1. Add OAuth2 library..."
    }
  ]
}
```

### Example 3: Large Ticket (Chunked)

```json
{
  "reference": "ISSUE-303",
  "question": "Very long question text that exceeds 3000 bytes... [continues for many paragraphs]",
  "metadata": {
    "title": "Complex Issue",
    "url": "https://issues.example.com/ISSUE-303"
  },
  "comments": [
    {
      "message": "Even longer comment with detailed technical explanation... [continues]"
    }
  ]
}
```

This will be automatically chunked into multiple entries with `chunk_index` and `total_chunks` metadata.

## See Also

- [GitLab Integration](GITLAB_INTEGRATION.md)
- [Search Features](SEARCH_FEATURES.md)
- [Configuration](CONFIGURATION.md)
- [CLI Reference](CLI_REFERENCE.md)
